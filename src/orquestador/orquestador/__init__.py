# Esqueleto del orquestador. Sin lógica de negocio: solo la app de Celery expuesta
# para infra/compose.yml (servicios "orquestador" y "worker"), configurada contra
# el Redis del propio stack (RF-01, RF-09, RF-12 — ver README.md de este módulo).
import os

from celery import Celery


def _redis_url(db: int = 0) -> str:
    host = os.environ.get("REDIS_HOST", "redis")
    port = os.environ.get("REDIS_PORT", "6379")
    password = os.environ.get("REDIS_PASSWORD", "")
    auth = f":{password}@" if password else ""
    return f"redis://{auth}{host}:{port}/{db}"


app = Celery("orquestador", broker=_redis_url(), backend=_redis_url())
