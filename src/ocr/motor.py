"""Motor de OCR por imagen (CU-06, Bloque 1): orienta, preprocesa y pasa por
Tesseract (spa+eng, OEM LSTM), devolviendo un `ResultadoPagina` con palabras
(texto, bbox, confianza), líneas en orden de lectura y confianza media.

`FuncionOcr` sigue el mismo patrón de inyección que `FuncionLLM`/
`FuncionRevisarLT` (`orquestador.pipeline_contable`/`pipeline_ortografia`):
las pruebas unitarias pasan un fake con un diccionario estilo
`pytesseract.image_to_data` y nunca invocan el binario real.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from ocr.modelos import Linea, Palabra, ResultadoPagina
from ocr.orientacion import FuncionOsd, corregir_orientacion
from ocr.preprocesamiento import DPI_MINIMO, preprocesar

FuncionOcr = Callable[[np.ndarray], dict[str, list[Any]]]


def ocr_imagen_tesseract(imagen: np.ndarray) -> dict[str, list[Any]]:
    """Implementación real: envuelve `pytesseract.image_to_data`. Import
    diferido (igual que `orientacion.detectar_rotacion_tesseract`) para que
    el resto del paquete se pueda probar sin el binario instalado."""
    import pytesseract

    return pytesseract.image_to_data(
        imagen, lang="spa+eng", config="--oem 1", output_type=pytesseract.Output.DICT
    )


def _agrupar_en_lineas(datos: dict[str, list[Any]]) -> tuple[list[Linea], list[Palabra]]:
    palabras_por_linea: dict[tuple[int, int, int], list[Palabra]] = {}
    orden_lineas: list[tuple[int, int, int]] = []
    todas: list[Palabra] = []

    textos = datos.get("text", [])
    for i in range(len(textos)):
        texto = (textos[i] or "").strip()
        if not texto:
            continue
        confianza = float(datos["conf"][i])
        if confianza < 0:
            continue
        palabra = Palabra(
            texto=texto,
            izquierda=int(datos["left"][i]),
            arriba=int(datos["top"][i]),
            ancho=int(datos["width"][i]),
            alto=int(datos["height"][i]),
            confianza=confianza,
        )
        clave = (int(datos["block_num"][i]), int(datos["par_num"][i]), int(datos["line_num"][i]))
        if clave not in palabras_por_linea:
            palabras_por_linea[clave] = []
            orden_lineas.append(clave)
        palabras_por_linea[clave].append(palabra)
        todas.append(palabra)

    # `orden_lineas` respeta el orden de inserción, que es el orden de
    # lectura con el que Tesseract ya emite sus filas -- sin ordenar aparte.
    lineas = [
        Linea(
            texto=" ".join(p.texto for p in palabras_por_linea[clave]),
            palabras=tuple(palabras_por_linea[clave]),
        )
        for clave in orden_lineas
    ]
    return lineas, todas


def _construir_resultado_pagina(
    numero: int,
    ancho_px: int,
    alto_px: int,
    datos: dict[str, list[Any]],
    *,
    texto_nativo: bool = False,
) -> ResultadoPagina:
    lineas, palabras = _agrupar_en_lineas(datos)
    confianza_media = sum(p.confianza for p in palabras) / len(palabras) if palabras else 0.0
    return ResultadoPagina(
        numero=numero,
        ancho_px=ancho_px,
        alto_px=alto_px,
        lineas=tuple(lineas),
        palabras=tuple(palabras),
        confianza_media=confianza_media,
        texto_nativo=texto_nativo,
    )


def procesar_imagen(
    imagen: np.ndarray,
    *,
    numero: int = 1,
    dpi_actual: float = DPI_MINIMO,
    funcion_ocr: FuncionOcr | None = None,
    funcion_osd: FuncionOsd | None = None,
) -> ResultadoPagina:
    """Corre el pipeline completo del Bloque 1 sobre una sola imagen ya
    decodificada: corrige orientación gruesa, preprocesa (deskew, ruido,
    binarización, escalado) y reconoce el texto."""
    orientada = corregir_orientacion(imagen, funcion_osd=funcion_osd)
    lista = preprocesar(orientada, dpi_actual=dpi_actual)
    funcion = funcion_ocr or ocr_imagen_tesseract
    datos = funcion(lista)
    alto_px, ancho_px = lista.shape[:2]
    return _construir_resultado_pagina(numero, ancho_px, alto_px, datos)
