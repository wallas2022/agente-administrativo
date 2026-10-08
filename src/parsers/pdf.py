"""Extractor de texto de PDF (RF-10, CU-05): texto por página y bloque, con
PyMuPDF. Solo lectura -- la revisión ortográfica vive en `src/ortografia`.
"""

from __future__ import annotations

import io

import pymupdf

from parsers.segmentos import SegmentoTexto


class PdfSinTextoError(Exception):
    """El PDF no tiene capa de texto extraíble (parece escaneado). CU-05 no
    inventa contenido a partir de la imagen -- CU-06 (OCR) sí puede
    procesarlo, como un análisis aparte que el usuario elige explícitamente
    (no se encadena en automático, ver docs/05-prompts/P-11-cu06-ocr-mvp.md)."""


def leer_texto_pdf(archivo: io.BytesIO | str) -> list[SegmentoTexto]:
    if isinstance(archivo, str):
        documento = pymupdf.open(archivo)
    else:
        archivo.seek(0)
        documento = pymupdf.open(stream=archivo.read(), filetype="pdf")

    try:
        segmentos: list[SegmentoTexto] = []
        for indice_pagina in range(1, documento.page_count + 1):
            pagina = documento[indice_pagina - 1]
            bloques = pagina.get_text("blocks")
            for indice_bloque, bloque in enumerate(bloques, start=1):
                texto = bloque[4].strip()
                if texto:
                    segmentos.append(
                        SegmentoTexto(
                            texto=texto,
                            ubicacion=f"Página {indice_pagina}, bloque {indice_bloque}",
                        )
                    )
    finally:
        documento.close()

    if not segmentos:
        raise PdfSinTextoError(
            "El PDF no tiene texto extraíble (parece escaneado); puede procesarse con "
            "\"Imagen a texto\" (OCR, CU-06) desde Nuevo análisis"
        )
    return segmentos
