"""Extractor de texto de PowerPoint (RF-10, CU-05): título, viñetas y notas
del orador por diapositiva. La revisión ortográfica vive en `src/ortografia`;
acá también vive aplicar las correcciones aceptadas (RF-14, Bloque O3) sobre
el mismo archivo, conservando el formato de cada corrida (`run`).
"""

from __future__ import annotations

import io
import re
from typing import Any

from pptx import Presentation

from parsers.correcciones import CorreccionAplicable, ResultadoCorreccion
from parsers.runs import reemplazar_texto_en_parrafo
from parsers.segmentos import SegmentoTexto


def _mapa_de_parrafos(diapositiva: Any) -> tuple[Any | None, dict[int, Any]]:
    """Recorre una diapositiva una sola vez y devuelve (párrafo del título o
    None, {número de viñeta: párrafo}) -- la extracción y la corrección usan
    exactamente el mismo recorrido para que la numeración de viñetas
    coincida siempre entre ambas.

    `shapes.title` construye un wrapper nuevo en cada acceso -- `is` nunca
    coincide con la forma del bucle aunque sea la misma diapositiva
    subyacente; `shape_id` sí es estable.
    """
    forma_titulo = diapositiva.shapes.title
    id_forma_titulo = forma_titulo.shape_id if forma_titulo is not None else None

    parrafo_titulo: Any | None = None
    vinetas: dict[int, Any] = {}
    contador_vineta = 0
    for forma in diapositiva.shapes:
        if not forma.has_text_frame:
            continue
        es_titulo = forma.shape_id == id_forma_titulo
        for parrafo in forma.text_frame.paragraphs:
            texto = "".join(corrida.text for corrida in parrafo.runs)
            if not texto.strip():
                continue
            if es_titulo:
                parrafo_titulo = parrafo
            else:
                contador_vineta += 1
                vinetas[contador_vineta] = parrafo

    return parrafo_titulo, vinetas


def leer_texto_pptx(archivo: io.BytesIO | str) -> list[SegmentoTexto]:
    if hasattr(archivo, "seek"):
        archivo.seek(0)
    presentacion = Presentation(archivo)

    segmentos: list[SegmentoTexto] = []
    for si, diapositiva in enumerate(presentacion.slides, start=1):
        parrafo_titulo, vinetas = _mapa_de_parrafos(diapositiva)
        if parrafo_titulo is not None:
            texto = "".join(c.text for c in parrafo_titulo.runs)
            segmentos.append(SegmentoTexto(texto=texto, ubicacion=f"Diapositiva {si}, título"))
        for numero, parrafo in vinetas.items():
            texto = "".join(c.text for c in parrafo.runs)
            segmentos.append(
                SegmentoTexto(texto=texto, ubicacion=f"Diapositiva {si}, viñeta {numero}")
            )

        if diapositiva.has_notes_slide:
            notas = diapositiva.notes_slide.notes_text_frame.text
            if notas.strip():
                segmentos.append(
                    SegmentoTexto(texto=notas, ubicacion=f"Diapositiva {si}, notas")
                )

    return segmentos


_PATRON_TITULO = re.compile(r"^Diapositiva (\d+), título$")
_PATRON_VINETA = re.compile(r"^Diapositiva (\d+), viñeta (\d+)$")
_PATRON_NOTAS = re.compile(r"^Diapositiva (\d+), notas$")


def _parrafos_candidatos(presentacion: Any, ubicacion: str) -> list[Any]:
    diapositivas = list(presentacion.slides)

    coincidencia = _PATRON_TITULO.match(ubicacion)
    if coincidencia:
        s = int(coincidencia.group(1))
        if not (1 <= s <= len(diapositivas)):
            return []
        titulo, _ = _mapa_de_parrafos(diapositivas[s - 1])
        return [titulo] if titulo is not None else []

    coincidencia = _PATRON_VINETA.match(ubicacion)
    if coincidencia:
        s, n = (int(x) for x in coincidencia.groups())
        if not (1 <= s <= len(diapositivas)):
            return []
        _, vinetas = _mapa_de_parrafos(diapositivas[s - 1])
        parrafo = vinetas.get(n)
        return [parrafo] if parrafo is not None else []

    coincidencia = _PATRON_NOTAS.match(ubicacion)
    if coincidencia:
        s = int(coincidencia.group(1))
        if not (1 <= s <= len(diapositivas)):
            return []
        diapositiva = diapositivas[s - 1]
        if not diapositiva.has_notes_slide:
            return []
        # Las notas se extrajeron como un solo segmento (texto completo del
        # cuadro), pero pueden tener varios párrafos -- se intenta cada uno.
        return list(diapositiva.notes_slide.notes_text_frame.paragraphs)

    return []


def aplicar_correcciones_pptx(
    archivo: io.BytesIO | str, correcciones: list[CorreccionAplicable]
) -> ResultadoCorreccion:
    if hasattr(archivo, "seek"):
        archivo.seek(0)
    presentacion = Presentation(archivo)

    no_aplicadas: list[CorreccionAplicable] = []
    for correccion in correcciones:
        candidatos = _parrafos_candidatos(presentacion, correccion.ubicacion)
        aplicada = any(
            reemplazar_texto_en_parrafo(p, correccion.texto_original, correccion.texto_nuevo)
            for p in candidatos
        )
        if not aplicada:
            no_aplicadas.append(correccion)

    buffer = io.BytesIO()
    presentacion.save(buffer)
    return ResultadoCorreccion(contenido=buffer.getvalue(), no_aplicadas=no_aplicadas)
