"""Pruebas del punto de entrada por documento de CU-06 (Bloque 1): imagen
suelta vs. PDF con páginas nativas y escaneadas mezcladas. `funcion_ocr`
siempre se reemplaza por un fake -- nunca se invoca el Tesseract real."""

from typing import Any

import cv2
import numpy as np
import pymupdf
import pytest

from ocr.documentos import decodificar_imagen, procesar_documento


def _png_bytes(ancho: int = 40, alto: int = 30) -> bytes:
    imagen = np.full((alto, ancho, 3), 255, dtype=np.uint8)
    ok, buffer = cv2.imencode(".png", imagen)
    assert ok
    return buffer.tobytes()


def _datos_ocr_falsos(texto: str = "Reconocido") -> dict[str, list[Any]]:
    return {
        "block_num": [1],
        "par_num": [1],
        "line_num": [1],
        "left": [5],
        "top": [5],
        "width": [30],
        "height": [10],
        "conf": [88.0],
        "text": [texto],
    }


def _no_deberia_llamarse(_img: np.ndarray) -> dict[str, list[Any]]:
    raise AssertionError("no debía llamarse al OCR real: la página tiene texto nativo")


def _pdf_con_texto_nativo() -> bytes:
    documento = pymupdf.open()
    pagina = documento.new_page()
    pagina.insert_text((72, 72), "Texto nativo de prueba, Q 1,250.00")
    contenido = documento.tobytes()
    documento.close()
    return contenido


def _pdf_escaneado_sin_texto() -> bytes:
    """Una página sin ninguna capa de texto -- solo una imagen insertada,
    como un PDF producido por un escáner."""
    documento = pymupdf.open()
    pagina = documento.new_page()
    pagina.insert_image(pagina.rect, stream=_png_bytes(200, 200))
    contenido = documento.tobytes()
    documento.close()
    return contenido


# --- decodificar_imagen --------------------------------------------------


def test_decodificar_imagen_valida() -> None:
    imagen = decodificar_imagen(_png_bytes())
    assert imagen.shape[:2] == (30, 40)


def test_decodificar_imagen_invalida_lanza_value_error() -> None:
    with pytest.raises(ValueError, match="no se pudo decodificar|no soportado"):
        decodificar_imagen(b"esto no es una imagen")


# --- procesar_documento: imagenes -----------------------------------------


def test_procesar_documento_imagen_llama_al_ocr_inyectado() -> None:
    resultados = procesar_documento(
        _png_bytes(),
        tipo_archivo="png",
        funcion_ocr=lambda _img: _datos_ocr_falsos("Hola"),
        funcion_osd=lambda _img: 0,
    )
    assert len(resultados) == 1
    assert resultados[0].texto == "Hola"
    assert resultados[0].texto_nativo is False


def test_procesar_documento_tipo_no_soportado_lanza_value_error() -> None:
    with pytest.raises(ValueError, match="no soportado"):
        procesar_documento(b"x", tipo_archivo="xlsx")


# --- procesar_documento: PDF -----------------------------------------------


def test_procesar_documento_pdf_con_texto_nativo_no_usa_ocr() -> None:
    resultados = procesar_documento(
        _pdf_con_texto_nativo(),
        tipo_archivo="pdf",
        funcion_ocr=_no_deberia_llamarse,
        funcion_osd=_no_deberia_llamarse,
    )
    assert len(resultados) == 1
    pagina = resultados[0]
    assert pagina.texto_nativo is True
    assert pagina.confianza_media == 100.0
    assert "Q 1,250.00" in pagina.texto


def test_procesar_documento_pdf_escaneado_rasteriza_y_usa_ocr() -> None:
    resultados = procesar_documento(
        _pdf_escaneado_sin_texto(),
        tipo_archivo="pdf",
        funcion_ocr=lambda _img: _datos_ocr_falsos("Escaneado"),
        funcion_osd=lambda _img: 0,
    )
    assert len(resultados) == 1
    pagina = resultados[0]
    assert pagina.texto_nativo is False
    assert pagina.texto == "Escaneado"
    # Rasterizado a 300 DPI (DPI_MINIMO): una página carta (612x792 pt) da
    # ~2550x3300 px -- bastante más grande que los 200x200 de la imagen
    # insertada, confirma que sí se rasterizó la página completa.
    assert pagina.ancho_px > 200
