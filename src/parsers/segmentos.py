"""Tipo compartido por los extractores de texto de CU-05 (RF-10): cada
extractor (docx, pptx, xlsx, pdf, texto plano) devuelve una lista de
`SegmentoTexto`, sin lógica de revisión ortográfica aquí -- eso lo hace
`src/ortografia` a partir de estos segmentos.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SegmentoTexto:
    """Un fragmento de texto con su ubicación exacta dentro del documento
    original. `ubicacion` usa coordenadas re-localizables en el propio
    archivo (p. ej. índice de párrafo, celda "Hoja!A1", número de
    diapositiva) para que, más adelante, aplicar una corrección pueda
    volver a encontrar el mismo lugar sin ambigüedad.
    """

    texto: str
    ubicacion: str
