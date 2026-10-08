"""Estructuras de datos del resultado de OCR por página (CU-06, Bloque 1).
Sin clasificación por umbral de confianza todavía -- eso es RN-06/Bloque 2
(`OCR_CONF_DUDOSA`, `OCR_CONF_REVISAR`, `OCR_PAGINA_ILEGIBLE`)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palabra:
    """Una palabra reconocida, con su posición (bbox, en píxeles de la
    imagen ya preprocesada) y confianza (0-100; -1 en texto nativo de PDF,
    donde no hay incertidumbre que reportar)."""

    texto: str
    izquierda: int
    arriba: int
    ancho: int
    alto: int
    confianza: float


@dataclass(frozen=True)
class Linea:
    """Una línea en orden de lectura, con sus palabras ya agrupadas."""

    texto: str
    palabras: tuple[Palabra, ...]


@dataclass(frozen=True)
class ResultadoPagina:
    """Resultado de una página completa (de una imagen suelta o de una
    página de un PDF). `texto_nativo=True` indica que el texto vino
    directamente de la capa de texto del PDF (PyMuPDF), no de Tesseract --
    no se inventa nada en ese caso, es texto real del documento."""

    numero: int
    ancho_px: int
    alto_px: int
    lineas: tuple[Linea, ...]
    palabras: tuple[Palabra, ...]
    confianza_media: float
    texto_nativo: bool = False

    @property
    def texto(self) -> str:
        return "\n".join(linea.texto for linea in self.lineas)
