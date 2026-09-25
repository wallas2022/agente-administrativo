"""Pipeline de CU-01 (Sprint 1, item 6): conecta parser → reglas → RAG →
explicación → salida. Lo invoca `tareas.ejecutar_analisis` cuando
`tipo_revision == "contable"`.

RNF-03: todo el cálculo (cuadre, cuentas, período, duplicados, moneda) lo hace
`validadores.contable.reglas`; el LLM solo redacta la explicación de los
hallazgos que lo requieren (ver `validadores.contable.explicacion`).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable
from pathlib import Path

from qdrant_client import QdrantClient
from sqlalchemy.orm import Session

from comun.modelos import Analisis, Documento, Hallazgo, VersionDocumento
from parsers.excel import leer_libro_contable
from rag.busqueda import buscar_fragmentos
from validadores.contable.explicacion import (
    REGLAS_AGRUPADAS,
    REGLAS_CON_LLM,
    ExplicacionGenerada,
    generar_explicacion_plantilla,
    generar_explicacion_plantilla_grupo,
    generar_explicaciones_lote,
)
from validadores.contable.reglas import HallazgoDetectado, validar_libro_contable
from validadores.contable.salida import marcar_celdas_en_libro


def _encontrar_raiz_con_kb(profundidad_maxima: int = 6) -> Path:
    """Busca hacia arriba desde este archivo un directorio que contenga `kb/`.

    La ubicación de `kb/` respecto a este módulo cambia según el entorno: en
    local, el paquete vive anidado en `src/orquestador/orquestador/` (3
    niveles bajo la raíz del repo); en la imagen Docker, `orquestador/Dockerfile`
    lo aplana a `/app/orquestador/` y copia `kb/` como `/app/kb/` (1 nivel).
    Recorrer hacia arriba evita hardcodear ese índice.
    """
    actual = Path(__file__).resolve().parent
    for _ in range(profundidad_maxima):
        if (actual / "kb").is_dir():
            return actual
        if actual.parent == actual:
            break
        actual = actual.parent
    raise FileNotFoundError(
        f"No se encontró un directorio 'kb/' subiendo desde {Path(__file__).resolve()}"
    )


def _ruta_catalogo_por_defecto() -> Path:
    return _encontrar_raiz_con_kb() / "kb" / "fuentes" / "catalogo-cuentas-contabilidad.csv"


COLECCION_RAG = "kb-contable"

FuncionEmbedding = Callable[[str], list[float]]
FuncionLLM = Callable[[str], str]


def cargar_catalogo(ruta: Path | None = None) -> set[str]:
    ruta_efectiva = ruta or _ruta_catalogo_por_defecto()
    with ruta_efectiva.open(encoding="utf-8") as archivo:
        return {fila["codigo"].strip() for fila in csv.DictReader(archivo)}


def _parsear_periodo_cierre(analisis: Analisis) -> tuple[int, int]:
    """RN-03 compara cada partida contra el período que se está cerrando
    (`Analisis.periodo_cierre`, "AAAA-MM"), no contra la fecha en que corre el
    análisis (`fecha_inicio`) — de lo contrario, revisar hoy un documento de
    un mes anterior dispararía RN-03 en casi todas las partidas.
    """
    if not analisis.periodo_cierre:
        raise ValueError(
            f"El análisis {analisis.id} no tiene periodo_cierre definido; "
            "requerido para validar RN-03 (fecha fuera de período)"
        )
    anio, mes = analisis.periodo_cierre.split("-")
    return int(anio), int(mes)


def _crear_fila_hallazgo(
    analisis: Analisis,
    version_original: VersionDocumento,
    hallazgo: HallazgoDetectado,
    explicacion: ExplicacionGenerada,
) -> Hallazgo:
    return Hallazgo(
        analisis_id=analisis.id,
        version_documento_id=version_original.id,
        severidad=hallazgo.severidad,
        ubicacion=hallazgo.ubicacion,
        descripcion=hallazgo.descripcion,
        correccion_sugerida=explicacion.texto,
        monto=hallazgo.monto,
        moneda=hallazgo.moneda,
        estado="pendiente",
        fuente_citada=explicacion.fuente_citada,
    )


def procesar_documento_contable(
    sesion: Session,
    *,
    documento: Documento,
    analisis: Analisis,
    version_original: VersionDocumento,
    contenido_original: bytes,
    cliente_qdrant: QdrantClient,
    funcion_embedding: FuncionEmbedding,
    funcion_llm: FuncionLLM,
    modelo_llm: str,
    subir_version_corregida: Callable[[str, bytes], None] | None = None,
    catalogo: set[str] | None = None,
    coleccion_rag: str | None = None,
) -> list[Hallazgo]:
    """Corre el pipeline completo sobre un libro contable ya descargado y
    persiste un `Hallazgo` por cada detección. Devuelve las filas creadas.

    RNF-04: la redacción con LLM es el costo dominante (ver
    docs/04-pruebas/resultados/local-S1.md), así que aquí solo pasan por el
    LLM los hallazgos de `REGLAS_CON_LLM` (RN-01, RN-05), agrupados en una
    ÚNICA llamada. El resto se explica por plantilla (sin LLM) y se
    persiste primero — visible de inmediato vía GET /analisis/{id}/hallazgos
    aunque el análisis siga "procesando" mientras se espera al LLM.
    """
    libro = leer_libro_contable(io.BytesIO(contenido_original))
    periodo = _parsear_periodo_cierre(analisis)
    detectados = validar_libro_contable(
        libro, catalogo=catalogo or cargar_catalogo(), periodo=periodo
    )

    # Totales reales del libro (Pantalla 3, U4) — se calculan siempre, haya o
    # no hallazgos, igual que el resto de RNF-03: suma simple, nunca el LLM.
    analisis.total_debe = sum(p.debe for p in libro.partidas)
    analisis.total_haber = sum(p.haber for p in libro.partidas)
    monedas_usadas = sorted({p.moneda for p in libro.partidas if p.moneda})
    analisis.moneda = "/".join(monedas_usadas) if monedas_usadas else None

    coleccion = coleccion_rag or COLECCION_RAG
    hallazgos_llm = [h for h in detectados if h.regla_codigo in REGLAS_CON_LLM]
    hallazgos_deterministas = [h for h in detectados if h.regla_codigo not in REGLAS_CON_LLM]

    filas: list[Hallazgo] = []

    # 1) Plantillas (sin LLM): RN-03/RN-04 agrupados, el resto individual.
    explicacion_por_regla_agrupada: dict[str, ExplicacionGenerada] = {}
    for regla in REGLAS_AGRUPADAS:
        del_grupo = [h for h in hallazgos_deterministas if h.regla_codigo == regla]
        if not del_grupo:
            continue
        fragmentos = buscar_fragmentos(
            cliente_qdrant,
            coleccion=coleccion,
            texto_consulta=del_grupo[0].descripcion,
            funcion_embedding=funcion_embedding,
        )
        explicacion_por_regla_agrupada[regla] = generar_explicacion_plantilla_grupo(
            del_grupo, fragmentos
        )

    for hallazgo in hallazgos_deterministas:
        explicacion = explicacion_por_regla_agrupada.get(hallazgo.regla_codigo)
        if explicacion is None:
            fragmentos = buscar_fragmentos(
                cliente_qdrant,
                coleccion=coleccion,
                texto_consulta=hallazgo.descripcion,
                funcion_embedding=funcion_embedding,
            )
            explicacion = generar_explicacion_plantilla(hallazgo, fragmentos)
        fila = _crear_fila_hallazgo(analisis, version_original, hallazgo, explicacion)
        sesion.add(fila)
        filas.append(fila)

    if filas:
        # Visibles de inmediato (RF-18) aunque falten los hallazgos con LLM.
        sesion.flush()
        sesion.commit()

    # 2) LLM (RN-01/RN-05): una sola llamada para todos, no una por hallazgo.
    if hallazgos_llm:
        items = [
            (
                h,
                buscar_fragmentos(
                    cliente_qdrant,
                    coleccion=coleccion,
                    texto_consulta=h.descripcion,
                    funcion_embedding=funcion_embedding,
                ),
            )
            for h in hallazgos_llm
        ]
        explicaciones = generar_explicaciones_lote(
            items, funcion_llm=funcion_llm, modelo=modelo_llm
        )
        for (hallazgo, _fragmentos), explicacion in zip(items, explicaciones, strict=True):
            fila = _crear_fila_hallazgo(analisis, version_original, hallazgo, explicacion)
            sesion.add(fila)
            filas.append(fila)
        analisis.modelo_llm = modelo_llm
        analisis.version_prompt = explicaciones[0].version_prompt

    if detectados and subir_version_corregida is not None:
        libro_marcado = marcar_celdas_en_libro(io.BytesIO(contenido_original), detectados)
        base, _, extension = version_original.ruta_almacenamiento.rpartition(".")
        llave_corregida = f"{base}.marcado.{extension or 'xlsx'}"
        subir_version_corregida(llave_corregida, libro_marcado)
        sesion.add(
            VersionDocumento(
                documento_id=documento.id,
                numero_version=version_original.numero_version + 1,
                ruta_almacenamiento=llave_corregida,
                es_corregida=True,
                fecha_creacion=analisis.fecha_inicio,
            )
        )

    sesion.flush()
    return filas
