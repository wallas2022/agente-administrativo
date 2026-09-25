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

RUTA_CATALOGO_POR_DEFECTO = (
    Path(__file__).resolve().parents[3] / "kb" / "fuentes" / "catalogo-cuentas-contabilidad.csv"
)
COLECCION_RAG = "kb-contable"

FuncionEmbedding = Callable[[str], list[float]]
FuncionLLM = Callable[[str], str]


def cargar_catalogo(ruta: Path = RUTA_CATALOGO_POR_DEFECTO) -> set[str]:
    with ruta.open(encoding="utf-8") as archivo:
        return {fila["codigo"].strip() for fila in csv.DictReader(archivo)}


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
) -> list[Hallazgo]:
    """Corre el pipeline completo sobre un libro contable ya descargado y
    persiste un `Hallazgo` por cada detección. Devuelve las filas creadas.
    """
    libro = leer_libro_contable(io.BytesIO(contenido_original))
    periodo = (analisis.fecha_inicio.year, analisis.fecha_inicio.month)
    detectados = validar_libro_contable(
        libro, catalogo=catalogo or cargar_catalogo(), periodo=periodo
    )

    filas: list[Hallazgo] = []
    for hallazgo in detectados:
        fragmentos = buscar_fragmentos(
            cliente_qdrant,
            coleccion=COLECCION_RAG,
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
