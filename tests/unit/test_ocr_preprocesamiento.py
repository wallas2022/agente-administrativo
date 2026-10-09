"""Pruebas del preprocesado OpenCV de CU-06 (Bloque 1): enderezado, reducción
de ruido, binarización adaptativa y escalado a ≥300 DPI. Todo con imágenes
sintéticas -- no requiere el binario de Tesseract."""

import cv2
import numpy as np

from ocr.preprocesamiento import (
    DPI_MINIMO,
    binarizar_adaptativa,
    calcular_angulo_inclinacion,
    enderezar,
    escalar_a_dpi_minimo,
    preprocesar,
    reducir_ruido,
)


def _imagen_rectangulo_rotado(angulo_grados: float) -> np.ndarray:
    lienzo = np.zeros((200, 200), dtype=np.uint8)
    cv2.rectangle(lienzo, (30, 95), (170, 105), 255, thickness=-1)
    matriz = cv2.getRotationMatrix2D((100, 100), angulo_grados, 1.0)
    return cv2.warpAffine(lienzo, matriz, (200, 200))


def _imagen_varias_lineas_horizontales() -> np.ndarray:
    """Varias "líneas de texto" (cada una con varias "palabras" separadas,
    no un bloque sólido -- más parecido a texto real) de ancho MUY
    distinto, perfectamente horizontales. Es el caso real que encontró el
    bug del dataset de CU-06 (Bloque 4): promediar todo el bloque con PCA
    daba un ángulo falso de ~6° en vez de 0°."""
    lienzo = np.zeros((300, 400), dtype=np.uint8)
    anchos_linea = [250, 90, 300, 150, 110, 260]
    rng = np.random.default_rng(7)
    for i, ancho_linea in enumerate(anchos_linea):
        y = 20 + i * 40
        x = 20
        fin_linea = 20 + ancho_linea
        while x < fin_linea:
            ancho_palabra = int(rng.integers(15, 35))
            cv2.rectangle(lienzo, (x, y), (min(x + ancho_palabra, fin_linea), y + 15), 255, -1)
            x += ancho_palabra + 8  # espacio entre palabras
    return lienzo


def test_calcular_angulo_inclinacion_imagen_vacia_da_cero() -> None:
    assert calcular_angulo_inclinacion(np.zeros((50, 50), dtype=np.uint8)) == 0.0


def test_calcular_angulo_inclinacion_detecta_rotacion() -> None:
    imagen = _imagen_rectangulo_rotado(12.0)
    angulo = calcular_angulo_inclinacion(imagen)
    assert abs(abs(angulo) - 12.0) < 1.5


def test_enderezar_reduce_la_inclinacion_detectada() -> None:
    imagen = _imagen_rectangulo_rotado(8.0)
    enderezada = enderezar(imagen)
    angulo_restante = calcular_angulo_inclinacion(enderezada)
    assert abs(angulo_restante) < 1.0


def test_calcular_angulo_inclinacion_no_se_confunde_con_varias_lineas_de_distinto_ancho() -> None:
    # Antes de la corrección (Bloque 4, dataset de CU-06: PCA sobre TODO el
    # bloque, no sobre una sola línea), este mismo caso daba ~6°-9° de
    # ángulo falso sobre un bloque perfectamente horizontal -- suficiente
    # para que `enderezar` rompiera glifos reales de Tesseract (CER
    # 0.53 -> 0.00, ver docs/04-pruebas/resultados/local-CU06.md).
    imagen = _imagen_varias_lineas_horizontales()
    angulo = calcular_angulo_inclinacion(imagen)
    assert abs(angulo) < 3.5


def test_enderezar_no_toca_una_imagen_ya_recta() -> None:
    imagen = _imagen_rectangulo_rotado(0.0)
    enderezada = enderezar(imagen)
    assert np.array_equal(imagen, enderezada)


def test_reducir_ruido_disminuye_el_ruido_sal_y_pimienta() -> None:
    rng = np.random.default_rng(42)
    base = np.full((100, 100), 200, dtype=np.uint8)
    mascara = rng.random(base.shape) < 0.1
    ruidosa = base.copy()
    ruidosa[mascara] = rng.choice([0, 255], size=int(mascara.sum()))

    limpia = reducir_ruido(ruidosa)

    diferencia_original = np.abs(ruidosa.astype(int) - base.astype(int)).sum()
    diferencia_limpia = np.abs(limpia.astype(int) - base.astype(int)).sum()
    assert diferencia_limpia < diferencia_original


def test_binarizar_adaptativa_devuelve_imagen_binaria() -> None:
    imagen = _imagen_rectangulo_rotado(0.0)
    binaria = binarizar_adaptativa(imagen)
    assert set(np.unique(binaria)).issubset({0, 255})


def test_escalar_a_dpi_minimo_agranda_imagenes_de_baja_resolucion() -> None:
    imagen = np.zeros((100, 200), dtype=np.uint8)
    escalada = escalar_a_dpi_minimo(imagen, dpi_actual=150)
    assert escalada.shape[0] > imagen.shape[0]
    assert escalada.shape[1] > imagen.shape[1]


def test_escalar_a_dpi_minimo_no_reduce_si_ya_cumple() -> None:
    imagen = np.zeros((100, 200), dtype=np.uint8)
    escalada = escalar_a_dpi_minimo(imagen, dpi_actual=DPI_MINIMO)
    assert escalada.shape == imagen.shape


def test_preprocesar_corre_el_pipeline_completo_sin_fallar() -> None:
    imagen = _imagen_rectangulo_rotado(5.0)
    resultado = preprocesar(imagen, dpi_actual=150)
    assert resultado.shape[0] >= imagen.shape[0]
    assert set(np.unique(resultado)).issubset({0, 255})
