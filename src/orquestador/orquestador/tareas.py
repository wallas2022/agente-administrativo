"""Tarea de Celery: consume la cola y transiciona el estado del documento/análisis.

Orquestación de estados de F1/L2 (docs/03-diseno/estados/estados-analisis.md).
Sprint 1 (CU-01) agrega el adaptador de `tipo_revision == "contable"`, que
delega en `pipeline_contable.procesar_documento_contable` (parser → reglas →
RAG → explicación → salida). Otros tipos de revisión siguen el flujo genérico
sin validadores hasta que se implementen sus propios adaptadores.
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


def _registrar_bitacora(
    sesion: Session, *, usuario_id: uuid.UUID, accion: str, entidad_id: uuid.UUID
) -> None:
    sesion.add(
        Bitacora(
            usuario_id=usuario_id,
            accion=accion,
            entidad_tipo="analisis",
            entidad_id=entidad_id,
            fecha_hora=datetime.now(UTC),
        )
    )


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
) -> str:
    """Lógica pura (sin Celery) para poder probarla con una sesión en memoria.

    Los parámetros de infraestructura (`cliente_s3`, `cliente_qdrant`, etc.)
    son opcionales: sin ellos, cualquier análisis (incluido uno contable) usa
    el flujo genérico sin validadores, como en L2.
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
    from rag.cliente_embeddings import obtener_embedding
    from rag.cliente_llm import generar_texto

    sesion = obtener_fabrica_sesion()()
    try:
        cliente_qdrant = None
        qdrant_url = os.environ.get("QDRANT_URL")
        if qdrant_url:
            from qdrant_client import QdrantClient

            cliente_qdrant = QdrantClient(url=qdrant_url)

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
        )
    finally:
        sesion.close()
