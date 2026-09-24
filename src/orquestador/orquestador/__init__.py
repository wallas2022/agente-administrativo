# Esqueleto del orquestador. Sin lógica de negocio: solo la app de Celery expuesta
# para infra/docker-compose.yml (servicios "orquestador" y "worker").
# Relacionado con: RF-01, RF-09, RF-12 (ver README.md de este módulo)
from celery import Celery

app = Celery("orquestador", broker=None, backend=None)   # [POR CONFIRMAR] URL de Redis
