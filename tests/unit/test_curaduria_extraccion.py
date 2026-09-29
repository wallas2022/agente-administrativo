from pathlib import Path

import pymupdf
import pytest

from curaduria.extraccion import (
    FORMATOS_SOPORTADOS,
    FragmentoExtraido,
    PdfSinTextoError,
    agrupar_por_seccion,
    extraer_fragmentos,
)
from parsers.segmentos import SegmentoTexto

RAIZ = Path(__file__).resolve().parents[2]
RUTA_PDF_EJEMPLO = RAIZ / "kb" / "plantillas" / "ejemplos" / "POL-001_Politica_Cierre_EJEMPLO.pdf"
RUTA_DOCX_EJEMPLO = RAIZ / "kb" / "plantillas" / "ejemplos" / "EST-001_Guia_Estilo_EJEMPLO.docx"


# --- documentos reales -------------------------------------------------------


def test_extraer_fragmentos_pdf_real_agrupa_las_6_secciones_por_pagina_1() -> None:
    fragmentos = extraer_fragmentos("pdf", RUTA_PDF_EJEMPLO.read_bytes())

    # El primer fragmento es el título/metadatos antes de "§1" (sin sección);
    # los siguientes 6 son las secciones reales del documento.
    secciones = [f.seccion for f in fragmentos]
    assert secciones[0] is None
    assert secciones[1:] == ["§1", "§2", "§3", "§4", "§5", "§6"]
    assert all(f.pagina == 1 for f in fragmentos)

    seccion_3 = next(f for f in fragmentos if f.seccion == "§3")
    assert "cuadrar" in seccion_3.contenido
    assert "§3" not in seccion_3.contenido  # el encabezado no se repite en el contenido


def test_extraer_fragmentos_docx_real_agrupa_las_4_secciones_sin_pagina() -> None:
    fragmentos = extraer_fragmentos("docx", RUTA_DOCX_EJEMPLO.read_bytes())

    # El primer fragmento es el título/versión antes de "§1" (sin sección).
    secciones = [f.seccion for f in fragmentos]
    assert secciones[0] is None
    assert secciones[1:] == ["§1", "§2", "§3", "§4"]
    assert all(f.pagina is None for f in fragmentos)

    seccion_4 = next(f for f in fragmentos if f.seccion == "§4")
    assert "sigla" in seccion_4.contenido.lower()


# --- PDF sin texto -----------------------------------------------------------


def test_extraer_fragmentos_pdf_sin_texto_requiere_ocr() -> None:
    documento = pymupdf.open()
    documento.new_page()
    contenido = documento.tobytes()
    documento.close()

    with pytest.raises(PdfSinTextoError, match="OCR"):
        extraer_fragmentos("pdf", contenido)


# --- Markdown -----------------------------------------------------------------


def test_extraer_fragmentos_md_usa_encabezados_seccion() -> None:
    texto = (
        "§1 Objetivo\n"
        "Primera línea del objetivo.\n"
        "Segunda línea del objetivo.\n"
        "§2 Alcance\n"
        "Contenido del alcance.\n"
    )
    fragmentos = extraer_fragmentos("md", texto.encode("utf-8"))

    assert [f.seccion for f in fragmentos] == ["§1", "§2"]
    assert "Primera línea" in fragmentos[0].contenido
    assert "Segunda línea" in fragmentos[0].contenido
    assert fragmentos[0].pagina is None


def test_extraer_fragmentos_md_cae_al_titulo_de_encabezado_sin_simbolo_seccion() -> None:
    texto = "## Introducción\nContenido de la introducción.\n## Alcance\nContenido del alcance.\n"
    fragmentos = extraer_fragmentos("md", texto.encode("utf-8"))

    assert [f.seccion for f in fragmentos] == ["Introducción", "Alcance"]


# --- sin marcas de sección: un solo fragmento --------------------------------


def test_agrupar_por_seccion_sin_encabezados_da_un_solo_fragmento() -> None:
    segmentos = [
        SegmentoTexto(texto="Primera idea.", ubicacion="Párrafo 0"),
        SegmentoTexto(texto="Segunda idea, sin encabezados de por medio.", ubicacion="Párrafo 1"),
    ]
    fragmentos = agrupar_por_seccion(segmentos)

    assert len(fragmentos) == 1
    assert fragmentos[0].seccion is None
    assert "Primera idea" in fragmentos[0].contenido
    assert "Segunda idea" in fragmentos[0].contenido


def test_agrupar_por_seccion_sin_segmentos_no_produce_fragmentos() -> None:
    assert agrupar_por_seccion([]) == []


# --- formato no soportado -----------------------------------------------------


def test_extraer_fragmentos_formato_no_soportado_lanza_value_error() -> None:
    with pytest.raises(ValueError, match="no soportado"):
        extraer_fragmentos("xlsx", b"contenido")


def test_formatos_soportados_expone_docx_pdf_md() -> None:
    assert FORMATOS_SOPORTADOS == {"docx", "pdf", "md"}


def test_fragmento_extraido_es_comparable_por_valor() -> None:
    assert FragmentoExtraido("x", "§1", None) == FragmentoExtraido("x", "§1", None)
