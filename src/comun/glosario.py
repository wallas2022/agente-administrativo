"""Carga del glosario interno (CU-05, RN-06; reutilizado por la fase 2 de
CU-02 -- RF-07) desde `kb/glosario/glosario.csv`. Vivía en
`orquestador.pipeline_ortografia`: se movió acá por la misma razón que
`comun.rutas_kb` (la API necesita el glosario sin importar el paquete
`orquestador`, que registra tareas de Celery al importarse).
"""

from __future__ import annotations

import csv
from pathlib import Path

from comun.rutas_kb import encontrar_raiz_con_kb


def _ruta_glosario_por_defecto() -> Path:
    return encontrar_raiz_con_kb() / "kb" / "glosario" / "glosario.csv"


def cargar_glosario(ruta: Path | None = None) -> set[str]:
    ruta_efectiva = ruta or _ruta_glosario_por_defecto()
    with ruta_efectiva.open(encoding="utf-8") as archivo:
        return {
            fila["termino"].strip() for fila in csv.DictReader(archivo) if fila.get("termino")
        }
