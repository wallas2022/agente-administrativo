"""Extracción de párrafos para CU-02 (RF-07): compartida entre el worker
(`orquestador.pipeline_redaccion`, fase 1) y la API (ruta SSE de fase 2 en
`api/main.py`, que necesita volver a extraer los mismos párrafos sin pasar
por el paquete `orquestador` -- ese paquete registra tareas de Celery al
importarse, algo que la API no debe arrastrar).
"""

from __future__ import annotations

import io
import re

from parsers.docx import leer_texto_docx
from parsers.pdf import leer_texto_pdf
from parsers.segmentos import SegmentoTexto
from parsers.texto_plano import leer_texto_plano

FORMATOS_SOPORTADOS = frozenset({"docx", "pdf", "txt"})

_PATRON_PARRAFO_EN_BLANCO = re.compile(r"\n\s*\n")


def _dividir_texto_plano_en_parrafos(texto: str) -> list[SegmentoTexto]:
    """`parsers.texto_plano.leer_texto_plano` devuelve el texto pegado
    completo en un solo `SegmentoTexto` (ubicacion="Texto") -- correcto
    para CU-05, que revisa todo el texto junto, pero CU-02 necesita
    streaming por párrafo. Se divide aquí, sin tocar el parser compartido."""
    partes = [p.strip() for p in _PATRON_PARRAFO_EN_BLANCO.split(texto) if p.strip()]
    if not partes:
        return []
    return [SegmentoTexto(texto=p, ubicacion=f"Párrafo {i + 1}") for i, p in enumerate(partes)]


def extraer_parrafos(tipo_archivo: str, contenido: bytes) -> list[SegmentoTexto]:
    """CU-02 solo cubre PDF/Word/texto (RF-07) -- a diferencia de CU-05, no
    incluye Excel ni PowerPoint."""
    extension = tipo_archivo.lower().lstrip(".")
    if extension == "docx":
        return leer_texto_docx(io.BytesIO(contenido))
    if extension == "pdf":
        return leer_texto_pdf(io.BytesIO(contenido))
    if extension == "txt":
        segmentos = leer_texto_plano(contenido.decode("utf-8", errors="replace"))
        if not segmentos:
            return []
        return _dividir_texto_plano_en_parrafos(segmentos[0].texto)
    raise ValueError(f"Formato no soportado para CU-02 (solo PDF/Word/texto): {tipo_archivo!r}")
