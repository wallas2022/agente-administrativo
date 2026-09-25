"""Pipeline de CU-01 (Sprint 1, item 6): conecta parser → reglas → RAG →
explicación → salida. Lo invoca `tareas.ejecutar_analisis` cuando
`tipo_revision == "contable"`.

RNF-03: todo el cálculo (cuadre, cuentas, período, duplicados, moneda) lo hace
`validadores.contable.reglas`; el LLM solo redacta la explicación de cada
hallazgo ya calculado.
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
from validadores.contable.explicacion import generar_explicacion
from validadores.contable.reglas import validar_libro_contable
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
    """
    libro = leer_libro_contable(io.BytesIO(contenido_original))
    periodo = _parsear_periodo_cierre(analisis)
    detectados = validar_libro_contable(
        libro, catalogo=catalogo or cargar_catalogo(), periodo=periodo
    )

    filas: list[Hallazgo] = []
    for hallazgo in detectados:
        fragmentos = buscar_fragmentos(
            cliente_qdrant,
            coleccion=coleccion_rag or COLECCION_RAG,
            texto_consulta=hallazgo.descripcion,
            funcion_embedding=funcion_embedding,
        )
        explicacion = generar_explicacion(
            hallazgo, fragmentos, funcion_llm=funcion_llm, modelo=modelo_llm
        )
        fila = Hallazgo(
            analisis_id=analisis.id,
            version_documento_id=version_original.id,
            severidad=hallazgo.severidad,
            ubicacion=hallazgo.ubicacion,
            descripcion=hallazgo.descripcion,
            correccion_sugerida=explicacion.texto,
            monto=hallazgo.monto,
            moneda=hallazgo.moneda,
            estado="pendiente",
        )
        sesion.add(fila)
        filas.append(fila)

    if detectados:
        analisis.modelo_llm = modelo_llm
        analisis.version_prompt = "redaccion-contable.v1"

        if subir_version_corregida is not None:
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
