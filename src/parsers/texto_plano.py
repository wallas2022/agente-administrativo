"""Extractor "trivial" para texto pegado directamente (RF-10, CU-05): no hay
archivo que parsear, pero se mantiene la misma interfaz `SegmentoTexto` que
el resto de extractores para que `src/ortografia` no distinga el origen.
"""

from __future__ import annotations

from parsers.segmentos import SegmentoTexto


def leer_texto_plano(texto: str) -> list[SegmentoTexto]:
    if not texto.strip():
        return []
    return [SegmentoTexto(texto=texto, ubicacion="Texto")]
