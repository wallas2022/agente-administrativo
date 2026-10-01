"""Ubicación de `kb/` en tiempo de ejecución -- compartido por los pipelines
de CU-01 (`kb/fuentes/catalogo-cuentas-contabilidad.csv`), CU-05 (`kb/
glosario/glosario.csv`) y la fase 2 de CU-02 (mismo glosario, ahora también
desde la API -- ver api/Dockerfile).

Vivía en `orquestador/rutas_kb.py`: se movió acá porque importar cualquier
submódulo de `orquestador` ejecuta `orquestador/__init__.py`, que registra
tareas de Celery -- algo que la API no debe arrastrar solo para leer un CSV.
"""

from __future__ import annotations

from pathlib import Path


def encontrar_raiz_con_kb(profundidad_maxima: int = 6) -> Path:
    """Busca hacia arriba desde este archivo un directorio que contenga `kb/`.

    La ubicación de `kb/` respecto a este módulo cambia según el entorno: en
    local, el paquete vive en `src/comun/` (2 niveles bajo la raíz del
    repo); en las imágenes Docker que la necesitan (`orquestador`, `worker`,
    `api`), su Dockerfile aplana todo a `/app/` y copia `kb/` como `/app/kb/`
    (1 nivel). Recorrer hacia arriba evita hardcodear ese índice.
    """
    actual = Path(__file__).resolve().parent
    for _ in range(profundidad_maxima):
        if (actual / "kb").is_dir():
            return actual
        if actual.parent == actual:
            break
        actual = actual.parent
    raise FileNotFoundError(
        f"No se encontró un directorio 'kb/' subiendo desde {Path(__file__).resolve()}"
    )
