"""Cola de trabajos (Celery + Redis) compartida por api (productor) y
orquestador/worker (consumidor). Sin lógica de negocio: solo la app de Celery.
"""

import os

from celery import Celery


def construir_url_redis(db: int = 0) -> str:
    host = os.environ.get("REDIS_HOST", "redis")
    port = os.environ.get("REDIS_PORT", "6379")
    password = os.environ.get("REDIS_PASSWORD", "")
    auth = f":{password}@" if password else ""
    return f"redis://{auth}{host}:{port}/{db}"


app = Celery("orquestador", broker=construir_url_redis(), backend=construir_url_redis())

NOMBRE_TAREA_ANALIZAR_DOCUMENTO = "orquestador.tareas.analizar_documento"
NOMBRE_TAREA_VALIDAR_DUDOSOS_ORTOGRAFIA = "orquestador.tareas.validar_dudosos_ortografia"


def encolar_analisis(documento_id: str, analisis_id: str) -> str:
    """Usado por la api para encolar un análisis sin importar el paquete orquestador."""
    resultado = app.send_task(
        NOMBRE_TAREA_ANALIZAR_DOCUMENTO,
        args=[documento_id, analisis_id],
    )
    return resultado.id


def encolar_validacion_dudosos_ortografia(analisis_id: str) -> str:
    """RNF-04 (Bloque O6): la propia fase 1 (`orquestador.tareas.ejecutar_analisis`)
    encola esto justo después de comitear el estado terminal del análisis,
    para que la validación LLM de los casos dudosos de CU-05 corra en
    segundo plano sin bloquear la publicación de los demás hallazgos."""
    resultado = app.send_task(
        NOMBRE_TAREA_VALIDAR_DUDOSOS_ORTOGRAFIA,
        args=[analisis_id],
    )
    return resultado.id
