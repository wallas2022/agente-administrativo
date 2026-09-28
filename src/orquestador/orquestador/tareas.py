"""Tarea de Celery: consume la cola y transiciona el estado del documento/análisis.

Orquestación de estados de F1/L2 (docs/03-diseno/estados/estados-analisis.md).
Sprint 1 (CU-01) agrega el adaptador de `tipo_revision == "contable"`, que
delega en `pipeline_contable.procesar_documento_contable` (parser → reglas →
RAG → explicación → salida). CU-05 (Bloque O4) agrega el de `"ortografia"`,
que delega en `pipeline_ortografia.procesar_documento_ortografia` (extracción
→ LanguageTool + glosario + LLM → persistencia). Otros tipos de revisión
siguen el flujo genérico sin validadores hasta que se implementen sus
propios adaptadores.
"""

import os
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from comun import almacenamiento
from comun.cola import app
from comun.db import obtener_fabrica_sesion
from comun.estados import EstadoAnalisis, EstadoDocumento
from comun.modelos import Analisis, Bitacora, Documento, TipoRevision, VersionDocumento
from orquestador.pipeline_contable import FuncionEmbedding, FuncionLLM, procesar_documento_contable
from orquestador.pipeline_ortografia import FuncionRevisarLT, procesar_documento_ortografia
from parsers.pdf import PdfSinTextoError


def _registrar_bitacora(
    sesion: Session,
    *,
    usuario_id: uuid.UUID,
    accion: str,
    entidad_id: uuid.UUID,
    detalle: str | None = None,
) -> None:
    sesion.add(
        Bitacora(
            usuario_id=usuario_id,
            accion=accion,
            entidad_tipo="analisis",
            entidad_id=entidad_id,
            fecha_hora=datetime.now(UTC),
            detalle=detalle,
        )
    )


def _marcar_fallido(
    sesion: Session, *, documento: Documento, analisis: Analisis, detalle: str
) -> str:
    """Cualquier error del pipeline (no solo PdfSinTextoError) marca el
    análisis "fallido" en vez de dejarlo atascado en "procesando" para
    siempre -- encontrado en vivo (Bloque O4): una caída transitoria de la
    conexión a Postgres a mitad de una inserción dejaba el análisis sin
    forma de que la UI supiera que algo salió mal. `rollback()` primero
    porque la sesión puede haber quedado en una transacción abortada (el
    pool ya usa `pool_pre_ping`, así que la siguiente consulta reconecta
    sola si la conexión murió)."""
    sesion.rollback()
    documento.estado = EstadoDocumento.FALLIDO.value
    analisis.estado = EstadoAnalisis.FALLIDO.value
    analisis.fecha_fin = datetime.now(UTC)
    _registrar_bitacora(
        sesion,
        usuario_id=analisis.usuario_id,
        accion="analisis_fallido",
        entidad_id=analisis.id,
        detalle=detalle,
    )
    sesion.commit()
    return documento.estado


def ejecutar_analisis(
    sesion: Session,
    documento_id: uuid.UUID,
    analisis_id: uuid.UUID,
    *,
    cliente_s3: object | None = None,
    bucket: str | None = None,
    cliente_qdrant: object | None = None,
    funcion_embedding: FuncionEmbedding | None = None,
    funcion_llm: FuncionLLM | None = None,
    modelo_llm: str | None = None,
    coleccion_rag: str | None = None,
    funcion_revisar_lt: FuncionRevisarLT | None = None,
) -> str:
    """Lógica pura (sin Celery) para poder probarla con una sesión en memoria.

    Los parámetros de infraestructura (`cliente_s3`, `cliente_qdrant`, etc.)
    son opcionales: sin ellos, cualquier análisis (incluido uno contable o de
    ortografía) usa el flujo genérico sin validadores, como en L2.
    """
    documento = sesion.get(Documento, documento_id)
    analisis = sesion.get(Analisis, analisis_id)
    if documento is None or analisis is None:
        return EstadoDocumento.FALLIDO.value

    documento.estado = EstadoDocumento.PROCESANDO.value
    _registrar_bitacora(
        sesion, usuario_id=analisis.usuario_id, accion="analisis_iniciado", entidad_id=analisis.id
    )
    sesion.commit()

    tipo_revision = sesion.get(TipoRevision, analisis.tipo_revision_id)
    version_original = (
        sesion.query(VersionDocumento)
        .filter_by(documento_id=documento.id)
        .order_by(VersionDocumento.numero_version.desc())
        .first()
    )

    hallazgos: list = []
    if (
        tipo_revision is not None
        and tipo_revision.nombre == "contable"
        and version_original is not None
        and cliente_s3 is not None
        and bucket is not None
        and cliente_qdrant is not None
        and funcion_embedding is not None
        and funcion_llm is not None
        and modelo_llm is not None
    ):
        contenido_original = almacenamiento.descargar_objeto(
            cliente_s3, bucket, version_original.ruta_almacenamiento
        )

        def _subir_version_corregida(llave: str, contenido: bytes) -> None:
            almacenamiento.subir_objeto(cliente_s3, bucket, llave, contenido)

        try:
            hallazgos = procesar_documento_contable(
                sesion,
                documento=documento,
                analisis=analisis,
                version_original=version_original,
                contenido_original=contenido_original,
                cliente_qdrant=cliente_qdrant,
                funcion_embedding=funcion_embedding,
                funcion_llm=funcion_llm,
                modelo_llm=modelo_llm,
                subir_version_corregida=_subir_version_corregida,
                coleccion_rag=coleccion_rag,
            )
        except Exception as error:  # ver _marcar_fallido
            return _marcar_fallido(
                sesion, documento=documento, analisis=analisis, detalle=str(error)
            )
    elif (
        tipo_revision is not None
        and tipo_revision.nombre == "ortografia"
        and version_original is not None
        and cliente_s3 is not None
        and bucket is not None
        and funcion_revisar_lt is not None
        and funcion_llm is not None
    ):
        contenido_original = almacenamiento.descargar_objeto(
            cliente_s3, bucket, version_original.ruta_almacenamiento
        )
        try:
            hallazgos = procesar_documento_ortografia(
                sesion,
                analisis=analisis,
                version_original=version_original,
                contenido_original=contenido_original,
                tipo_archivo=documento.tipo_archivo,
                funcion_revisar_lt=funcion_revisar_lt,
                funcion_llm=funcion_llm,
            )
        except PdfSinTextoError as error:
            # Mensaje amable y específico (no inventa nada: refleja RF-11 --
            # "requiere OCR, iteración 2" -- en vez del str() genérico de
            # cualquier otra excepción).
            return _marcar_fallido(
                sesion, documento=documento, analisis=analisis, detalle=str(error)
            )
        except Exception as error:  # ver _marcar_fallido
            return _marcar_fallido(
                sesion, documento=documento, analisis=analisis, detalle=str(error)
            )

    documento.estado = (
        EstadoDocumento.CON_HALLAZGOS.value if hallazgos else EstadoDocumento.EN_REVISION.value
    )
    analisis.estado = EstadoAnalisis.COMPLETADO.value
    analisis.fecha_fin = datetime.now(UTC)
    _registrar_bitacora(
        sesion,
        usuario_id=analisis.usuario_id,
        accion="analisis_completado",
        entidad_id=analisis.id,
    )
    sesion.commit()
    return documento.estado


@app.task(name="orquestador.tareas.analizar_documento")
def analizar_documento(documento_id: str, analisis_id: str) -> str:
    from ortografia.cliente_languagetool import revisar_texto
    from rag.cliente_embeddings import obtener_embedding
    from rag.cliente_llm import generar_texto

    sesion = obtener_fabrica_sesion()()
    try:
        from qdrant_client import QdrantClient

        qdrant_host = os.environ.get("QDRANT_HOST", "qdrant")
        qdrant_port = os.environ.get("QDRANT_PORT", "6333")
        cliente_qdrant = QdrantClient(url=f"http://{qdrant_host}:{qdrant_port}")

        return ejecutar_analisis(
            sesion,
            uuid.UUID(documento_id),
            uuid.UUID(analisis_id),
            cliente_s3=almacenamiento.obtener_cliente_s3(),
            bucket=os.environ.get("MINIO_BUCKET_DOCUMENTOS", "documentos"),
            cliente_qdrant=cliente_qdrant,
            funcion_embedding=obtener_embedding,
            funcion_llm=generar_texto,
            modelo_llm=os.environ.get("LLM_MODEL_PRINCIPAL", ""),
            coleccion_rag=os.environ.get("QDRANT_COLECCION"),
            funcion_revisar_lt=revisar_texto,
        )
    finally:
        sesion.close()
