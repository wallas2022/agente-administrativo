"""Pruebas de la corrección de orientación gruesa (OSD) de CU-06 (Bloque 1).
`funcion_osd` se reemplaza por un fake -- nunca se invoca el Tesseract real
en estas pruebas (mismo patrón que `FuncionLLM`/`FuncionRevisarLT`)."""

import numpy as np

from ocr.orientacion import corregir_orientacion


def _imagen_asimetrica() -> np.ndarray:
    imagen = np.zeros((40, 100), dtype=np.uint8)
    imagen[5:15, 5:30] = 255  # marca en una esquina para distinguir orientación
    return imagen


def test_corregir_orientacion_sin_rotacion_devuelve_la_misma_imagen() -> None:
    imagen = _imagen_asimetrica()
    resultado = corregir_orientacion(imagen, funcion_osd=lambda _img: 0)
    assert np.array_equal(resultado, imagen)


def test_corregir_orientacion_90_grados_rota_las_dimensiones() -> None:
    imagen = _imagen_asimetrica()
    resultado = corregir_orientacion(imagen, funcion_osd=lambda _img: 90)
    assert resultado.shape == (imagen.shape[1], imagen.shape[0])


def test_corregir_orientacion_180_grados_mantiene_dimensiones() -> None:
    imagen = _imagen_asimetrica()
    resultado = corregir_orientacion(imagen, funcion_osd=lambda _img: 180)
    assert resultado.shape == imagen.shape
    assert not np.array_equal(resultado, imagen)


def test_corregir_orientacion_270_grados_rota_las_dimensiones() -> None:
    imagen = _imagen_asimetrica()
    resultado = corregir_orientacion(imagen, funcion_osd=lambda _img: 270)
    assert resultado.shape == (imagen.shape[1], imagen.shape[0])
