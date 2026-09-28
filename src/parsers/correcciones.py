"""Tipos compartidos para aplicar correcciones ortográficas aceptadas al
documento original (RF-14, CU-05, Bloque O3). Independientes de cómo se
persistan las decisiones del Revisor (CU-07) -- ese cableado vive en el
orquestador, no acá.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CorreccionAplicable:
    """Una corrección ya aceptada por el Revisor, lista para aplicarse.
    `ubicacion` debe ser exactamente la que produjo el extractor original
    (`parsers.segmentos.SegmentoTexto.ubicacion`) para poder re-ubicar el
    mismo lugar en el archivo."""

    ubicacion: str
    texto_original: str
    texto_nuevo: str


@dataclass(frozen=True)
class ResultadoCorreccion:
    """`no_aplicadas` deja rastro de qué correcciones no se pudieron aplicar
    (ubicación ya no existe, o el texto original ya no está ahí) -- mejor
    un documento con algunas correcciones de menos que fallar todo el
    proceso o aplicar algo en el lugar equivocado."""

    contenido: bytes
    no_aplicadas: list[CorreccionAplicable] = field(default_factory=list)
