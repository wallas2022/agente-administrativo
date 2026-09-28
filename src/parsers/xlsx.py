"""Extractor de texto de Excel genérico (RF-10, CU-05): celdas de texto de
cualquier hoja, sin asumir un esquema de columnas -- distinto de
`parsers.excel` (CU-01), que sí asume el esquema contable Cuenta|Descripcion|
...|Moneda. Solo lectura -- la revisión ortográfica vive en `src/ortografia`.
"""

from __future__ import annotations

import io

from openpyxl import load_workbook

from parsers.segmentos import SegmentoTexto


def leer_texto_xlsx(archivo: io.BytesIO | str) -> list[SegmentoTexto]:
    """Extrae solo celdas de texto: excluye fórmulas (se leen del libro sin
    `data_only` para detectarlas por `data_type == "f"`, sin importar si el
    resultado cacheado de la fórmula es texto) y celdas numéricas."""
    if hasattr(archivo, "seek"):
        archivo.seek(0)
    libro_formulas = load_workbook(archivo, data_only=False)
    if hasattr(archivo, "seek"):
        archivo.seek(0)
    libro_valores = load_workbook(archivo, data_only=True)

    segmentos: list[SegmentoTexto] = []
    for nombre_hoja in libro_formulas.sheetnames:
        hoja_formulas = libro_formulas[nombre_hoja]
        hoja_valores = libro_valores[nombre_hoja]
        filas = zip(hoja_formulas.iter_rows(), hoja_valores.iter_rows(), strict=True)
        for fila_formulas, fila_valores in filas:
            celdas = zip(fila_formulas, fila_valores, strict=True)
            for celda_formula, celda_valor in celdas:
                if celda_formula.data_type == "f":
                    continue
                valor = celda_valor.value
                if isinstance(valor, str) and valor.strip():
                    segmentos.append(
                        SegmentoTexto(
                            texto=valor,
                            ubicacion=f"{nombre_hoja}!{celda_valor.coordinate}",
                        )
                    )
    return segmentos
