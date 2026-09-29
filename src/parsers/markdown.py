"""Extractor de texto de Markdown (RF-16, CU-08): reutiliza `SegmentoTexto`
(mismo tipo que docx/pdf/texto plano de CU-05) para que `curaduria.
extraccion` pueda agrupar por sección con la misma lógica sin importar el
formato de origen. Solo lectura -- CU-08 no reescribe fuentes normativas,
así que no hay `aplicar_correcciones_md`.
"""

from __future__ import annotations

from parsers.segmentos import SegmentoTexto


def leer_texto_md(texto: str) -> list[SegmentoTexto]:
    return [
        SegmentoTexto(texto=linea.strip(), ubicacion=f"Línea {numero}")
        for numero, linea in enumerate(texto.splitlines(), start=1)
        if linea.strip()
    ]
