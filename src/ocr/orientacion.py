"""Detección de orientación gruesa (OSD: 0/90/180/270°) y su corrección
(CU-06, Bloque 1). A diferencia del enderezado fino de `ocr.preprocesamiento`
(ángulos pequeños, puro OpenCV), esto sí necesita el motor de Tesseract --
por eso la función real queda inyectable (`FuncionOsd`), siguiendo el mismo
patrón de `FuncionLLM`/`FuncionRevisarLT` ya usado en
`orquestador.pipeline_contable`/`pipeline_ortografia`: las pruebas unitarias
pasan un fake y nunca invocan el binario real.
"""

from __future__ import annotations

from collections.abc import Callable

import cv2
import numpy as np

FuncionOsd = Callable[[np.ndarray], int]

_ROTACIONES = {
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


def detectar_rotacion_tesseract(imagen: np.ndarray) -> int:
    """Implementación real: envuelve `pytesseract.image_to_osd`. Solo se
    importa acá (no a nivel de módulo) para que el resto de `ocr` se pueda
    probar sin tener el binario de Tesseract instalado."""
    import pytesseract

    datos = pytesseract.image_to_osd(imagen, output_type=pytesseract.Output.DICT)
    return int(datos.get("rotate", 0)) % 360


def corregir_orientacion(
    imagen: np.ndarray, *, funcion_osd: FuncionOsd | None = None
) -> np.ndarray:
    """Rota la imagen el múltiplo de 90° que haga falta para que quede
    "de pie", según lo que reporte `funcion_osd` (0 si ya está correcta)."""
    funcion = funcion_osd or detectar_rotacion_tesseract
    rotacion = funcion(imagen) % 360

    codigo = _ROTACIONES.get(rotacion)
    if codigo is None:
        return imagen
    return cv2.rotate(imagen, codigo)
