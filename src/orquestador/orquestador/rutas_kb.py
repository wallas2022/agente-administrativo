"""Ubicación de `kb/` en tiempo de ejecución -- compartido por los pipelines
de CU-01 (`kb/fuentes/catalogo-cuentas-contabilidad.csv`) y CU-05
(`kb/glosario/glosario.csv`).
"""

from __future__ import annotations

from pathlib import Path


def encontrar_raiz_con_kb(profundidad_maxima: int = 6) -> Path:
    """Busca hacia arriba desde este archivo un directorio que contenga `kb/`.

    La ubicación de `kb/` respecto a este módulo cambia según el entorno: en
    local, el paquete vive anidado en `src/orquestador/orquestador/` (3
    niveles bajo la raíz del repo); en la imagen Docker, `orquestador/Dockerfile`
    lo aplana a `/app/orquestador/` y copia `kb/` como `/app/kb/` (1 nivel).
    Recorrer hacia arriba evita hardcodear ese índice.
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
