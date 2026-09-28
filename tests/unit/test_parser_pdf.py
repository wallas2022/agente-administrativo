import io

import pymupdf
import pytest

from parsers.pdf import PdfSinTextoError, leer_texto_pdf


def _pdf_de_prueba() -> bytes:
    documento = pymupdf.open()
    pagina1 = documento.new_page()
    pagina1.insert_text((72, 72), "Primer bloque de la página 1")
    pagina1.insert_text((72, 200), "Segundo bloque de la página 1")
    documento.new_page().insert_text((72, 72), "Único bloque de la página 2")
    contenido = documento.tobytes()
    documento.close()
    return contenido


def _pdf_sin_texto() -> bytes:
    documento = pymupdf.open()
    documento.new_page()  # página en blanco, sin insertar texto
    contenido = documento.tobytes()
    documento.close()
    return contenido


def test_extrae_texto_por_pagina_y_bloque() -> None:
    segmentos = leer_texto_pdf(io.BytesIO(_pdf_de_prueba()))

    ubicaciones = {s.ubicacion for s in segmentos}
    assert "Página 1, bloque 1" in ubicaciones
    assert "Página 2, bloque 1" in ubicaciones
    assert any("Segundo bloque" in s.texto for s in segmentos)


def test_pdf_sin_capa_de_texto_lanza_error_explicito() -> None:
    with pytest.raises(PdfSinTextoError, match="OCR"):
        leer_texto_pdf(io.BytesIO(_pdf_sin_texto()))
