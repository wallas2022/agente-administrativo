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


def encolar_analisis(documento_id: str, analisis_id: str) -> str:
    """Usado por la api para encolar un análisis sin importar el paquete orquestador."""
    resultado = app.send_task(
        NOMBRE_TAREA_ANALIZAR_DOCUMENTO,
        args=[documento_id, analisis_id],
    )
    return resultado.id
