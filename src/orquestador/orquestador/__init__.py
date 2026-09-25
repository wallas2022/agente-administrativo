# Orquestador: consume la cola y ejecuta el flujo de análisis (sin lógica de
# negocio real todavía — la aplican los validadores en Sprint 1). Reexporta la
# app de Celery compartida con "comun.cola" (usada también por la api como
# productora) para que ambos hablen el mismo broker y el mismo nombre de tarea.
from comun.cola import app

from . import tareas  # noqa: F401  (registra las tareas en `app`)

__all__ = ["app"]
