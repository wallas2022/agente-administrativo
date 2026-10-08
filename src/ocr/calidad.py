"""Clasificación de confianza y detección de páginas ilegibles (CU-06,
Bloque 2, RN-06): nunca se inventa texto -- una página cuya confianza media
no alcanza el umbral se informa como ilegible (cero texto) en vez de
publicar un reconocimiento poco confiable (PP-06).

Los umbrales son configuración (`.env`), no código: `OCR_CONF_DUDOSA`
(rojo), `OCR_CONF_REVISAR` (amarillo) y `OCR_PAGINA_ILEGIBLE` (confianza
media mínima de una página completa).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from ocr.modelos import ResultadoPagina

NIVEL_DUDOSA = "dudosa"
NIVEL_REVISAR = "revisar"
NIVEL_OK = "ok"

_DEFECTO_CONF_DUDOSA = 60.0
_DEFECTO_CONF_REVISAR = 80.0
_DEFECTO_PAGINA_ILEGIBLE = 50.0


@dataclass(frozen=True)
class Umbrales:
    conf_dudosa: float = _DEFECTO_CONF_DUDOSA
    conf_revisar: float = _DEFECTO_CONF_REVISAR
    pagina_ilegible: float = _DEFECTO_PAGINA_ILEGIBLE


def umbrales_desde_entorno() -> Umbrales:
    return Umbrales(
        conf_dudosa=float(os.environ.get("OCR_CONF_DUDOSA", _DEFECTO_CONF_DUDOSA)),
        conf_revisar=float(os.environ.get("OCR_CONF_REVISAR", _DEFECTO_CONF_REVISAR)),
        pagina_ilegible=float(os.environ.get("OCR_PAGINA_ILEGIBLE", _DEFECTO_PAGINA_ILEGIBLE)),
    )


def clasificar_confianza(confianza: float, umbrales: Umbrales) -> str:
    """Nivel de una palabra: "dudosa" (rojo) < `conf_dudosa`, "revisar"
    (amarillo) < `conf_revisar`, si no "ok"."""
    if confianza < umbrales.conf_dudosa:
        return NIVEL_DUDOSA
    if confianza < umbrales.conf_revisar:
        return NIVEL_REVISAR
    return NIVEL_OK


def es_pagina_ilegible(pagina: ResultadoPagina, umbrales: Umbrales) -> bool:
    """Una página con texto nativo de PDF nunca es "ilegible" -- es texto
    real, no un reconocimiento. Para páginas de OCR: ilegible si no se
    reconoció ninguna palabra, o si la confianza media no alcanza el
    umbral."""
    if pagina.texto_nativo:
        return False
    if not pagina.palabras:
        return True
    return pagina.confianza_media < umbrales.pagina_ilegible
