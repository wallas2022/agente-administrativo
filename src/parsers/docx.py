"""Extractor de texto de Word (RF-10, CU-05). Solo lectura y normalización
-- la revisión ortográfica vive en `src/ortografia`.

`ubicacion` guarda el índice de párrafo/tabla tal como los expone
python-docx (`documento.paragraphs[i]`, `documento.tables[t]`), para que
aplicar una corrección más adelante (RF-14) pueda volver a abrir el mismo
archivo y ubicar el mismo párrafo o celda sin ambigüedad.
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from typing import Any

from docx import Document

from parsers.segmentos import SegmentoTexto


def _segmentos_de_parrafos(
    parrafos: Iterable[Any], prefijo_ubicacion: str
) -> list[SegmentoTexto]:
    return [
        SegmentoTexto(texto=p.text, ubicacion=f"{prefijo_ubicacion} {i}")
        for i, p in enumerate(parrafos)
        if p.text.strip()
    ]


def _segmentos_de_encabezado_pie(secciones: Iterable[Any]) -> list[SegmentoTexto]:
    segmentos: list[SegmentoTexto] = []
    for si, seccion in enumerate(secciones, start=1):
        segmentos += _segmentos_de_parrafos(
            seccion.header.paragraphs, f"Encabezado {si}, párrafo"
        )
        segmentos += _segmentos_de_parrafos(
            seccion.footer.paragraphs, f"Pie de página {si}, párrafo"
        )
    return segmentos


def leer_texto_docx(archivo: io.BytesIO | str) -> list[SegmentoTexto]:
    if hasattr(archivo, "seek"):
        archivo.seek(0)
    documento = Document(archivo)

    segmentos = _segmentos_de_parrafos(documento.paragraphs, "Párrafo")

    for ti, tabla in enumerate(documento.tables, start=1):
        for fi, fila in enumerate(tabla.rows, start=1):
            for ci, celda in enumerate(fila.cells, start=1):
                if celda.text.strip():
                    segmentos.append(
                        SegmentoTexto(
                            texto=celda.text,
                            ubicacion=f"Tabla {ti}, fila {fi}, columna {ci}",
                        )
                    )

    segmentos += _segmentos_de_encabezado_pie(documento.sections)
    return segmentos
