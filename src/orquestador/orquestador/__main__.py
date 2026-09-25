"""Punto de entrada del servicio "orquestador" (distinto de "worker", que
corre `celery -A orquestador worker`).

[NOTA DE ARQUITECTURA] Con la implementación de L2, toda la orquestación real
(consumir la cola, transicionar estados, registrar bitácora — ver
orquestador/tareas.py) corre en el proceso Celery del servicio "worker". Este
proceso queda como esqueleto para tareas futuras de mantenimiento (p. ej. un
scheduler tipo Celery beat para el job periódico de retención de RN-08/RNF-12,
ver docs/03-diseno/flujos/pipeline-validacion.md, subgrafo RETENCION) — hoy
solo evita el bucle de reinicio que tenía en F1 (imprimía y terminaba).
"""

import signal
import sys
import time


def _manejar_señal_de_apagado(signum: int, frame: object) -> None:
    sys.exit(0)


def main() -> None:
    signal.signal(signal.SIGTERM, _manejar_señal_de_apagado)
    print("Orquestador — esqueleto en espera (ver nota de arquitectura arriba).")
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
