"""Preprocesado de imagen antes de pasarla a Tesseract (CU-06, Bloque 1):
enderezado (deskew), reducción de ruido, binarización adaptativa y escalado
a ≥300 DPI. Todo con OpenCV puro -- no requiere el binario de Tesseract, así
que se puede probar con imágenes sintéticas sin depender de la instalación
del sistema (ver docs/02-analisis/04-analisis-cu06-ocr.md).

La detección de orientación gruesa (0/90/180/270, OSD) vive aparte, en
`ocr.orientacion`, porque esa sí necesita Tesseract.
"""

from __future__ import annotations

import cv2
import numpy as np

DPI_MINIMO = 300


def _a_escala_grises(imagen: np.ndarray) -> np.ndarray:
    if imagen.ndim == 2:
        return imagen
    return cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)


def _bandas_de_texto(mascara: np.ndarray, *, separacion_minima: int = 3) -> list[tuple[int, int]]:
    """Agrupa filas contiguas con contenido en "bandas" (cada banda ≈ una
    línea de texto), separando dos bandas cuando hay al menos
    `separacion_minima` filas vacías seguidas entre ellas."""
    densidad_filas = mascara.sum(axis=1)
    bandas: list[tuple[int, int]] = []
    inicio: int | None = None
    vacias_seguidas = 0
    for y, tiene_contenido in enumerate(densidad_filas > 0):
        if tiene_contenido:
            if inicio is None:
                inicio = y
            vacias_seguidas = 0
        elif inicio is not None:
            vacias_seguidas += 1
            if vacias_seguidas >= separacion_minima:
                bandas.append((inicio, y - vacias_seguidas))
                inicio = None
    if inicio is not None:
        bandas.append((inicio, len(densidad_filas) - 1))
    return bandas


def calcular_angulo_inclinacion(imagen: np.ndarray) -> float:
    """Ángulo (grados, en el rango (-45, 45]) que hay que corregir para
    enderezar el texto. Usa PCA sobre los píxeles de primer plano de UNA
    sola línea de texto (la más densa) -- no de todo el bloque. Promediar
    varias líneas de distinto largo (encontrado con el dataset de CU-06,
    Bloque 4: un párrafo de 6 líneas, perfectamente horizontal, daba un
    "ángulo" falso de -6°, y enderezarlo de más rompía los caracteres)
    arrastra ruido que una sola línea bien elegida no tiene. Una inclinación
    de página real (escaneo torcido) afecta a todas las líneas por igual,
    así que una sola basta como referencia."""
    gris = _a_escala_grises(imagen)
    _, binaria = cv2.threshold(gris, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)

    bandas = _bandas_de_texto(binaria)
    if not bandas:
        return 0.0
    inicio, fin = max(bandas, key=lambda banda: int(binaria[banda[0] : banda[1] + 1, :].sum()))
    recorte = binaria[inicio : fin + 1, :]

    coordenadas = cv2.findNonZero(recorte)
    if coordenadas is None or len(coordenadas) < 2:
        return 0.0

    puntos = coordenadas.reshape(-1, 2).astype(np.float32)  # columnas: (x, y)
    media = np.mean(puntos, axis=0).reshape(1, -1)
    _media, autovectores = cv2.PCACompute(puntos, mean=media, maxComponents=1)
    vector_x, vector_y = autovectores[0]
    angulo = float(np.degrees(np.arctan2(vector_y, vector_x)))

    # Normaliza a (-45, 45]: el autovector no distingue 0° de 180°, así que
    # cualquier ángulo fuera de ese rango describe la misma línea.
    while angulo <= -45:
        angulo += 90
    while angulo > 45:
        angulo -= 90
    return angulo


def enderezar(imagen: np.ndarray, *, tolerancia_grados: float = 0.1) -> np.ndarray:
    """Corrige inclinaciones finas (deskew). La corrección gruesa de
    orientación (90/180/270°) la hace `ocr.orientacion.corregir_orientacion`
    antes de llegar acá."""
    angulo = calcular_angulo_inclinacion(imagen)
    if abs(angulo) < tolerancia_grados:
        return imagen

    alto, ancho = imagen.shape[:2]
    centro = (ancho / 2, alto / 2)
    matriz = cv2.getRotationMatrix2D(centro, angulo, 1.0)
    borde = (
        int(np.mean(imagen))
        if imagen.ndim == 2
        else tuple(int(c) for c in imagen.mean(axis=(0, 1)))
    )
    return cv2.warpAffine(
        imagen,
        matriz,
        (ancho, alto),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=borde,
    )


def reducir_ruido(imagen: np.ndarray) -> np.ndarray:
    """Elimina ruido tipo sal-y-pimienta sin borrar los trazos finos de las
    letras -- `fastNlMeansDenoising` conserva bordes mejor que un blur
    gaussiano simple para texto escaneado."""
    gris = _a_escala_grises(imagen)
    return cv2.fastNlMeansDenoising(gris, h=10, templateWindowSize=7, searchWindowSize=21)


def binarizar_adaptativa(imagen: np.ndarray) -> np.ndarray:
    """Umbral adaptativo (no uno global): tolera iluminación despareja en
    fotos de documentos, a diferencia de un único umbral Otsu para toda la
    página."""
    gris = _a_escala_grises(imagen)
    return cv2.adaptiveThreshold(
        gris,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31,
        C=15,
    )


def escalar_a_dpi_minimo(
    imagen: np.ndarray, dpi_actual: float, dpi_minimo: int = DPI_MINIMO
) -> np.ndarray:
    """Escala hacia arriba si la imagen viene por debajo de `dpi_minimo`
    (Tesseract pierde exactitud con menos de 300 DPI). Nunca reduce: una
    imagen que ya cumple el mínimo se devuelve tal cual."""
    if dpi_actual <= 0 or dpi_actual >= dpi_minimo:
        return imagen
    factor = dpi_minimo / dpi_actual
    alto, ancho = imagen.shape[:2]
    nuevo_tamano = (round(ancho * factor), round(alto * factor))
    return cv2.resize(imagen, nuevo_tamano, interpolation=cv2.INTER_CUBIC)


def preprocesar(imagen: np.ndarray, *, dpi_actual: float = DPI_MINIMO) -> np.ndarray:
    """Orquesta el preprocesado completo en el orden del Bloque 1: escalado
    → enderezado → reducción de ruido → binarización adaptativa."""
    escalada = escalar_a_dpi_minimo(imagen, dpi_actual)
    enderezada = enderezar(escalada)
    sin_ruido = reducir_ruido(enderezada)
    return binarizar_adaptativa(sin_ruido)
