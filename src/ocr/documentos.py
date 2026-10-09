"""Punto de entrada de CU-06 (Bloque 1): procesa un archivo completo (imagen
suelta o PDF) y devuelve un `ResultadoPagina` por página. En un PDF, las
páginas con texto nativo se usan tal cual (PyMuPDF, sin pasar por Tesseract
-- no hay nada que "reconocer", ya es texto real); las páginas sin texto se
rasterizan a 300 DPI y sí pasan por el motor de OCR (`ocr.motor`).
"""

from __future__ import annotations

import cv2
import numpy as np
import pymupdf

from ocr.capturas import (
    ALTURA_MINIMA_LINEA_CAPTURA,
    altura_media_linea,
    es_captura_de_pantalla,
    leer_dpi,
)
from ocr.modelos import Linea, Palabra, ResultadoPagina
from ocr.motor import FuncionOcr, procesar_imagen, procesar_imagen_captura
from ocr.orientacion import FuncionOsd
from ocr.preprocesamiento import DPI_MINIMO

EXTENSIONES_IMAGEN = {"png", "jpg", "jpeg", "tiff", "tif", "bmp"}
CONFIANZA_TEXTO_NATIVO = 100.0


def decodificar_imagen(contenido: bytes) -> np.ndarray:
    arreglo = np.frombuffer(contenido, dtype=np.uint8)
    imagen = cv2.imdecode(arreglo, cv2.IMREAD_COLOR)
    if imagen is None:
        raise ValueError("No se pudo decodificar la imagen (formato no soportado o archivo dañado)")
    return imagen


def _resultado_texto_nativo(numero: int, pagina: pymupdf.Page) -> ResultadoPagina:
    """Página de PDF con capa de texto real -- se usa tal cual (RNF-03: nunca
    se inventa ni se re-reconoce lo que el propio PDF ya afirma que dice)."""
    rect = pagina.rect
    palabras_crudas = pagina.get_text("words")  # (x0, y0, x1, y1, texto, bloque, linea, palabra)

    palabras: list[Palabra] = []
    lineas_por_clave: dict[tuple[int, int], list[Palabra]] = {}
    orden_lineas: list[tuple[int, int]] = []
    for x0, y0, x1, y1, texto, bloque, num_linea, _num_palabra in palabras_crudas:
        if not texto.strip():
            continue
        palabra = Palabra(
            texto=texto,
            izquierda=round(x0),
            arriba=round(y0),
            ancho=round(x1 - x0),
            alto=round(y1 - y0),
            confianza=CONFIANZA_TEXTO_NATIVO,
        )
        palabras.append(palabra)
        clave = (int(bloque), int(num_linea))
        if clave not in lineas_por_clave:
            lineas_por_clave[clave] = []
            orden_lineas.append(clave)
        lineas_por_clave[clave].append(palabra)

    lineas = [
        Linea(
            texto=" ".join(p.texto for p in lineas_por_clave[clave]),
            palabras=tuple(lineas_por_clave[clave]),
        )
        for clave in orden_lineas
    ]
    return ResultadoPagina(
        numero=numero,
        ancho_px=round(rect.width),
        alto_px=round(rect.height),
        lineas=tuple(lineas),
        palabras=tuple(palabras),
        confianza_media=CONFIANZA_TEXTO_NATIVO,
        texto_nativo=True,
    )


def _pixmap_a_bgr(pixmap: pymupdf.Pixmap) -> np.ndarray:
    canal = max(pixmap.n, 1)
    # pixmap.height/.width son enteros en tiempo de ejecución; los stubs de
    # PyMuPDF los declaran mal (como si fueran métodos).
    alto, ancho = int(pixmap.height), int(pixmap.width)  # type: ignore[call-overload]
    arreglo = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(alto, ancho, canal)
    if canal == 1:
        return cv2.cvtColor(arreglo, cv2.COLOR_GRAY2BGR)
    if canal == 4:
        return cv2.cvtColor(arreglo, cv2.COLOR_RGBA2BGR)
    return cv2.cvtColor(arreglo, cv2.COLOR_RGB2BGR)


def procesar_pdf(
    contenido: bytes,
    *,
    funcion_ocr: FuncionOcr | None = None,
    funcion_osd: FuncionOsd | None = None,
) -> list[ResultadoPagina]:
    documento = pymupdf.open(stream=contenido, filetype="pdf")
    try:
        resultados: list[ResultadoPagina] = []
        for indice in range(documento.page_count):
            pagina = documento[indice]
            numero = indice + 1
            if pagina.get_text().strip():
                resultados.append(_resultado_texto_nativo(numero, pagina))
            else:
                pixmap = pagina.get_pixmap(dpi=DPI_MINIMO)
                imagen = _pixmap_a_bgr(pixmap)
                resultados.append(
                    procesar_imagen(
                        imagen,
                        numero=numero,
                        dpi_actual=DPI_MINIMO,
                        funcion_ocr=funcion_ocr,
                        funcion_osd=funcion_osd,
                    )
                )
        return resultados
    finally:
        documento.close()


def procesar_documento(
    contenido: bytes,
    *,
    tipo_archivo: str,
    funcion_ocr: FuncionOcr | None = None,
    funcion_osd: FuncionOsd | None = None,
) -> list[ResultadoPagina]:
    extension = tipo_archivo.lower().lstrip(".")
    if extension in EXTENSIONES_IMAGEN:
        imagen = decodificar_imagen(contenido)
        if es_captura_de_pantalla(dpi=leer_dpi(contenido), imagen=imagen):
            return [procesar_imagen_captura(imagen, numero=1, funcion_ocr=funcion_ocr)]
        resultado = procesar_imagen(
            imagen, numero=1, funcion_ocr=funcion_ocr, funcion_osd=funcion_osd
        )
        # Bloque 2b: ni DPI ni fondo delataron una captura, pero la letra
        # consistentemente chica sí -- p. ej. una captura con una textura de
        # fondo que no quedó perfectamente plana. Se reintenta con el
        # preprocesado de capturas en vez de quedarse con un resultado
        # probablemente pobre del preprocesado pensado para papel escaneado.
        if 0 < altura_media_linea(resultado) < ALTURA_MINIMA_LINEA_CAPTURA:
            return [
                procesar_imagen_captura(imagen, numero=1, funcion_ocr=funcion_ocr)
            ]
        return [resultado]
    if extension == "pdf":
        return procesar_pdf(contenido, funcion_ocr=funcion_ocr, funcion_osd=funcion_osd)
    raise ValueError(f"Tipo de archivo no soportado para OCR: {tipo_archivo!r}")
