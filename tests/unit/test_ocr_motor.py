"""Pruebas del motor de OCR por imagen (CU-06, Bloque 1). `funcion_ocr` y
`funcion_osd` se reemplazan por fakes -- nunca se invoca el Tesseract real."""

from typing import Any

import numpy as np

from ocr.motor import procesar_imagen

IMAGEN = np.zeros((80, 50), dtype=np.uint8)


def _datos_tesseract_falsos() -> dict[str, list[Any]]:
    # Filas de nivel página/bloque/párrafo/línea (conf=-1, sin texto) +
    # palabras reales de dos líneas, a propósito fuera de orden de índice
    # para confirmar que el agrupado respeta el orden de lectura de Tesseract
    # (el orden en que vienen las filas), no un reordenamiento propio.
    return {
        "block_num": [0, 1, 1, 1, 1, 1, 1, 2],
        "par_num": [0, 1, 1, 1, 1, 1, 2, 1],
        "line_num": [0, 1, 1, 1, 1, 1, 1, 1],
        "left": [0, 0, 0, 0, 10, 60, 10, 10],
        "top": [0, 0, 0, 0, 10, 10, 30, 60],
        "width": [50, 50, 50, 50, 40, 30, 40, 40],
        "height": [80, 80, 20, 20, 15, 15, 15, 15],
        "conf": [-1, -1, -1, -1, 95.5, 80.2, 60.0, 10.0],
        "text": ["", "", "", "", "Hola", "Mundo", "Adiós", "Q"],
    }


def test_procesar_imagen_agrupa_palabras_en_lineas_en_orden_de_lectura() -> None:
    resultado = procesar_imagen(
        IMAGEN, funcion_ocr=lambda _img: _datos_tesseract_falsos(), funcion_osd=lambda _img: 0
    )

    assert [linea.texto for linea in resultado.lineas] == ["Hola Mundo", "Adiós", "Q"]
    assert resultado.texto == "Hola Mundo\nAdiós\nQ"
    assert len(resultado.palabras) == 4


def test_procesar_imagen_calcula_la_confianza_media_solo_de_las_palabras() -> None:
    resultado = procesar_imagen(
        IMAGEN, funcion_ocr=lambda _img: _datos_tesseract_falsos(), funcion_osd=lambda _img: 0
    )
    esperado = (95.5 + 80.2 + 60.0 + 10.0) / 4
    assert abs(resultado.confianza_media - esperado) < 0.01


def test_procesar_imagen_conserva_bbox_y_confianza_por_palabra() -> None:
    resultado = procesar_imagen(
        IMAGEN, funcion_ocr=lambda _img: _datos_tesseract_falsos(), funcion_osd=lambda _img: 0
    )
    hola = resultado.palabras[0]
    assert hola.texto == "Hola"
    assert (hola.izquierda, hola.arriba, hola.ancho, hola.alto) == (10, 10, 40, 15)
    assert hola.confianza == 95.5


def test_procesar_imagen_sin_palabras_da_confianza_cero_y_sin_lineas() -> None:
    datos_vacios: dict[str, list[Any]] = {
        "block_num": [],
        "par_num": [],
        "line_num": [],
        "left": [],
        "top": [],
        "width": [],
        "height": [],
        "conf": [],
        "text": [],
    }
    resultado = procesar_imagen(
        IMAGEN, funcion_ocr=lambda _img: datos_vacios, funcion_osd=lambda _img: 0
    )
    assert resultado.confianza_media == 0.0
    assert resultado.lineas == ()
    assert resultado.palabras == ()


def test_procesar_imagen_numero_de_pagina_se_conserva() -> None:
    resultado = procesar_imagen(
        IMAGEN,
        numero=3,
        funcion_ocr=lambda _img: _datos_tesseract_falsos(),
        funcion_osd=lambda _img: 0,
    )
    assert resultado.numero == 3
