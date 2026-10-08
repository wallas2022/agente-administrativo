"""Tarea de Celery: consume la cola y transiciona el estado del documento/análisis.

Orquestación de estados de F1/L2 (docs/03-diseno/estados/estados-analisis.md).
Sprint 1 (CU-01) agrega el adaptador de `tipo_revision == "contable"`, que
delega en `pipeline_contable.procesar_documento_contable` (parser → reglas →
RAG → explicación → salida). CU-05 (Bloque O4) agrega el de `"ortografia"`,
que delega en `pipeline_ortografia.procesar_documento_ortografia` (extracción
→ LanguageTool + glosario + LLM → persistencia). CU-06 (Bloque 1) agrega el
de `"ocr"`, que delega en `pipeline_ocr.procesar_documento_ocr` (imagen/PDF
→ Tesseract → nueva versión con el texto reconocido). Otros tipos de
revisión siguen el flujo genérico sin validadores hasta que se implementen
sus propios adaptadores.
"""

import logging
import os
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from comun import almacenamiento
from comun.cola import app
from comun.db import obtener_fabrica_sesion
from comun.estados import EstadoAnalisis, EstadoDocumento
from comun.modelos import Analisis, Bitacora, Documento, Hallazgo, TipoRevision, VersionDocumento
from orquestador.pipeline_contable import FuncionEmbedding, FuncionLLM, procesar_documento_contable
from orquestador.pipeline_ocr import FuncionOcr, FuncionOsd, procesar_documento_ocr
from orquestador.pipeline_ortografia import (
    FuncionRevisarLT,
    extraer_segmentos,
    procesar_documento_ortografia,
    resolver_dudosos_ortografia,
)
from orquestador.pipeline_redaccion import procesar_documento_redaccion
from parsers.pdf import PdfSinTextoError

FuncionEncolarValidacionDudosos = Callable[[str], str]


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
    funcion_encolar_validacion_dudosos: FuncionEncolarValidacionDudosos | None = None,
    funcion_ocr: FuncionOcr | None = None,
    funcion_osd: FuncionOsd | None = None,
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
    dudosos: list[Hallazgo] = []
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
    ):
        contenido_original = almacenamiento.descargar_objeto(
            cliente_s3, bucket, version_original.ruta_almacenamiento
        )
        try:
            # Fase 1 (RNF-04, Bloque O6): solo LanguageTool + glosario --
            # publica de inmediato, sin esperar al LLM.
            deterministas, dudosos, contexto_por_ubicacion = procesar_documento_ortografia(
                sesion,
                analisis=analisis,
                version_original=version_original,
                contenido_original=contenido_original,
                tipo_archivo=documento.tipo_archivo,
                funcion_revisar_lt=funcion_revisar_lt,
            )
            hallazgos = deterministas + dudosos
            if dudosos and funcion_encolar_validacion_dudosos is None and funcion_llm is not None:
                # Sin forma de encolar en segundo plano (p. ej. pruebas o un
                # entorno sin Celery): resuelve los dudosos ya mismo, para no
                # cambiar el comportamiento donde nadie pidió la fase 2 async.
                resolver_dudosos_ortografia(
                    sesion,
                    hallazgos=dudosos,
                    contexto_por_ubicacion=contexto_por_ubicacion,
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
    elif (
        tipo_revision is not None
        and tipo_revision.nombre == "redaccion"
        and version_original is not None
        and cliente_s3 is not None
        and bucket is not None
    ):
        # Fase 1 (determinista, sin LLM) -- ver docs/02-analisis/
        # 02-analisis-cu02-redaccion-amigable.md §2.1. La fase 2 (LLM por
        # párrafo, streaming) NO corre acá: el frontend la dispara aparte
        # contra GET /analisis/{id}/mejorar-stream apenas aterriza en la
        # pantalla de resultados.
        contenido_original = almacenamiento.descargar_objeto(
            cliente_s3, bucket, version_original.ruta_almacenamiento
        )
        try:
            hallazgos, _parrafos = procesar_documento_redaccion(
                sesion,
                analisis=analisis,
                version_original=version_original,
                contenido_original=contenido_original,
                tipo_archivo=documento.tipo_archivo,
                tipo_documento=analisis.tipo_documento or "",
            )
        except PdfSinTextoError as error:
            return _marcar_fallido(
                sesion, documento=documento, analisis=analisis, detalle=str(error)
            )
        except Exception as error:  # ver _marcar_fallido
            return _marcar_fallido(
                sesion, documento=documento, analisis=analisis, detalle=str(error)
            )
    elif (
        tipo_revision is not None
        and tipo_revision.nombre == "ocr"
        and version_original is not None
        and cliente_s3 is not None
        and bucket is not None
    ):
        # Fase 1 (MVP, Bloque 1): sin clasificación de confianza ni
        # hallazgos de "palabra dudosa" todavía (RN-06/Bloque 2) -- solo
        # corre el motor y publica el texto reconocido como nueva versión.
        contenido_original = almacenamiento.descargar_objeto(
            cliente_s3, bucket, version_original.ruta_almacenamiento
        )

        def _subir_version_texto(llave: str, contenido: bytes) -> None:
            almacenamiento.subir_objeto(cliente_s3, bucket, llave, contenido)

        try:
            procesar_documento_ocr(
                sesion,
                analisis=analisis,
                version_original=version_original,
                contenido_original=contenido_original,
                tipo_archivo=documento.tipo_archivo,
                subir_version_texto=_subir_version_texto,
                funcion_ocr=funcion_ocr,
                funcion_osd=funcion_osd,
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

    if dudosos and funcion_encolar_validacion_dudosos is not None:
        # Recién después de comitear el estado terminal (RNF-04, Bloque O6):
        # la tarea en segundo plano corre en otra sesión/proceso y debe ver
        # los hallazgos "en_validacion" ya persistidos.
        funcion_encolar_validacion_dudosos(str(analisis.id))

    return documento.estado


@app.task(name="orquestador.tareas.analizar_documento")
def analizar_documento(documento_id: str, analisis_id: str) -> str:
    from comun.cola import encolar_validacion_dudosos_ortografia
    from ocr.motor import ocr_imagen_tesseract
    from ocr.orientacion import detectar_rotacion_tesseract
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
            funcion_encolar_validacion_dudosos=encolar_validacion_dudosos_ortografia,
            funcion_ocr=ocr_imagen_tesseract,
            funcion_osd=detectar_rotacion_tesseract,
        )
    finally:
        sesion.close()


def ejecutar_validacion_dudosos_ortografia(
    sesion: Session,
    analisis_id: uuid.UUID,
    *,
    cliente_s3: object,
    bucket: str,
    funcion_llm: FuncionLLM,
) -> None:
    """Lógica pura (sin Celery) de la fase 2 -- mismo patrón que
    `ejecutar_analisis`, para poder probarla con una sesión en memoria. El
    análisis ya llegó a un estado terminal en la fase 1 (RNF-04, Bloque O6):
    un error acá NO lo revierte -- los hallazgos afectados simplemente
    quedan "en_validacion" (documentado en la bitácora) en vez de "fallido"."""
    analisis = sesion.get(Analisis, analisis_id)
    if analisis is None:
        return

    hallazgos = (
        sesion.query(Hallazgo).filter_by(analisis_id=analisis.id, estado="en_validacion").all()
    )
    if not hallazgos:
        return

    documento = sesion.get(Documento, analisis.documento_id)
    if documento is None:
        return
    version_original = (
        sesion.query(VersionDocumento)
        .filter_by(documento_id=documento.id)
        .order_by(VersionDocumento.numero_version.desc())
        .first()
    )
    if version_original is None:
        return
    try:
        contenido_original = almacenamiento.descargar_objeto(
            cliente_s3, bucket, version_original.ruta_almacenamiento
        )
        contexto_por_ubicacion = {
            s.ubicacion: s.texto
            for s in extraer_segmentos(documento.tipo_archivo, contenido_original)
        }
        resolver_dudosos_ortografia(
            sesion,
            hallazgos=hallazgos,
            contexto_por_ubicacion=contexto_por_ubicacion,
            funcion_llm=funcion_llm,
        )
        _registrar_bitacora(
            sesion,
            usuario_id=analisis.usuario_id,
            accion="ortografia_dudosos_validados",
            entidad_id=analisis.id,
            detalle=f"{len(hallazgos)} caso(s) dudoso(s) resuelto(s) por el LLM",
        )
        sesion.commit()
    except Exception as error:
        # Encontrado en vivo (Bloque O6): con la BD ya inestable por la misma
        # presión de memoria documentada en local-S1/S2, el propio
        # rollback()/commit() de este bloque puede fallar también -- sin
        # este segundo try/except, esa segunda falla se propaga sin control
        # y revienta la tarea de Celery (los hallazgos quedan "en_validacion"
        # sin ningún rastro de qué pasó, el mismo problema de raíz que
        # _marcar_fallido ya resuelve para la fase 1).
        detalle = str(error)
        try:
            sesion.rollback()
            _registrar_bitacora(
                sesion,
                usuario_id=analisis.usuario_id,
                accion="ortografia_dudosos_fallo",
                entidad_id=analisis.id,
                detalle=detalle,
            )
            sesion.commit()
        except Exception:
            logging.getLogger(__name__).exception(
                "No se pudo registrar en la bitácora el fallo de validación de "
                "dudosos de analisis_id=%s (detalle original: %s)",
                analisis_id,
                detalle,
            )


@app.task(name="orquestador.tareas.validar_dudosos_ortografia")
def validar_dudosos_ortografia(analisis_id: str) -> None:
    from rag.cliente_llm import generar_texto

    sesion = obtener_fabrica_sesion()()
    try:
        modelo_ortografia = os.environ.get("LLM_MODEL_ORTOGRAFIA") or os.environ.get(
            "LLM_MODEL_PRINCIPAL", ""
        )

        def _funcion_llm(prompt: str) -> str:
            return generar_texto(prompt, modelo=modelo_ortografia)

        ejecutar_validacion_dudosos_ortografia(
            sesion,
            uuid.UUID(analisis_id),
            cliente_s3=almacenamiento.obtener_cliente_s3(),
            bucket=os.environ.get("MINIO_BUCKET_DOCUMENTOS", "documentos"),
            funcion_llm=_funcion_llm,
        )
    finally:
        sesion.close()
