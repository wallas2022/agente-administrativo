"""Extractor "trivial" para texto pegado directamente (RF-10, CU-05): no hay
archivo que parsear, pero se mantiene la misma interfaz `SegmentoTexto` que
el resto de extractores para que `src/ortografia` no distinga el origen.
"""

from __future__ import annotations

from parsers.correcciones import CorreccionAplicable
from parsers.segmentos import SegmentoTexto


def leer_texto_plano(texto: str) -> list[SegmentoTexto]:
    if not texto.strip():
        return []
    return [SegmentoTexto(texto=texto, ubicacion="Texto")]


def aplicar_correcciones_texto_plano(texto: str, correcciones: list[CorreccionAplicable]) -> str:
    for correccion in correcciones:
        if correccion.ubicacion == "Texto" and correccion.texto_original in texto:
            texto = texto.replace(correccion.texto_original, correccion.texto_nuevo, 1)
    return texto
