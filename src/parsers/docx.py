"""Extractor de texto de Word (RF-10, CU-05). Solo lectura y normalización
-- la revisión ortográfica vive en `src/ortografia`.

`ubicacion` guarda el índice de párrafo/tabla tal como los expone
python-docx (`documento.paragraphs[i]`, `documento.tables[t]`), para que
aplicar una corrección más adelante (RF-14) pueda volver a abrir el mismo
archivo y ubicar el mismo párrafo o celda sin ambigüedad.
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterable
from typing import Any

from docx import Document

from parsers.correcciones import CorreccionAplicable, ResultadoCorreccion
from parsers.runs import reemplazar_texto_en_parrafo
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


_PATRON_PARRAFO = re.compile(r"^Párrafo (\d+)$")
_PATRON_TABLA = re.compile(r"^Tabla (\d+), fila (\d+), columna (\d+)$")
_PATRON_ENCABEZADO = re.compile(r"^Encabezado (\d+), párrafo (\d+)$")
_PATRON_PIE = re.compile(r"^Pie de página (\d+), párrafo (\d+)$")


def _parrafos_candidatos(documento: Any, ubicacion: str) -> list[Any]:
    """Devuelve los párrafos donde podría estar el texto de esa ubicación.
    Para una celda de tabla o un encabezado/pie con varios párrafos, la
    extracción (`leer_texto_docx`) concatenó todo en un solo segmento --
    acá se intenta cada párrafo hasta encontrar el que de verdad contiene
    el texto a corregir (ver `reemplazar_texto_en_parrafo`)."""
    coincidencia = _PATRON_PARRAFO.match(ubicacion)
    if coincidencia:
        indice = int(coincidencia.group(1))
        parrafos = documento.paragraphs
        return [parrafos[indice]] if 0 <= indice < len(parrafos) else []

    coincidencia = _PATRON_TABLA.match(ubicacion)
    if coincidencia:
        t, f, c = (int(x) for x in coincidencia.groups())
        tablas = documento.tables
        if not (1 <= t <= len(tablas)):
            return []
        tabla = tablas[t - 1]
        if not (1 <= f <= len(tabla.rows)) or not (1 <= c <= len(tabla.columns)):
            return []
        return list(tabla.rows[f - 1].cells[c - 1].paragraphs)

    coincidencia = _PATRON_ENCABEZADO.match(ubicacion)
    if coincidencia:
        s, indice = (int(x) for x in coincidencia.groups())
        secciones = documento.sections
        if not (1 <= s <= len(secciones)):
            return []
        parrafos = secciones[s - 1].header.paragraphs
        return [parrafos[indice]] if 0 <= indice < len(parrafos) else []

    coincidencia = _PATRON_PIE.match(ubicacion)
    if coincidencia:
        s, indice = (int(x) for x in coincidencia.groups())
        secciones = documento.sections
        if not (1 <= s <= len(secciones)):
            return []
        parrafos = secciones[s - 1].footer.paragraphs
        return [parrafos[indice]] if 0 <= indice < len(parrafos) else []

    return []


def aplicar_correcciones_docx(
    archivo: io.BytesIO | str, correcciones: list[CorreccionAplicable]
) -> ResultadoCorreccion:
    if hasattr(archivo, "seek"):
        archivo.seek(0)
    documento = Document(archivo)

    no_aplicadas: list[CorreccionAplicable] = []
    for correccion in correcciones:
        candidatos = _parrafos_candidatos(documento, correccion.ubicacion)
        aplicada = any(
            reemplazar_texto_en_parrafo(p, correccion.texto_original, correccion.texto_nuevo)
            for p in candidatos
        )
        if not aplicada:
            no_aplicadas.append(correccion)

    buffer = io.BytesIO()
    documento.save(buffer)
    return ResultadoCorreccion(contenido=buffer.getvalue(), no_aplicadas=no_aplicadas)


def construir_docx_desde_segmentos(
    segmentos: list[SegmentoTexto], correcciones: list[CorreccionAplicable]
) -> bytes:
    """Para PDF (RF-14): no se reescribe el archivo original -- se entrega un
    .docx nuevo con el texto extraído y las correcciones aceptadas ya
    aplicadas, un párrafo por segmento (con su ubicación original como
    referencia, para que el reporte de "qué se corrigió" siga siendo claro)."""
    correcciones_por_ubicacion = {c.ubicacion: c for c in correcciones}

    documento = Document()
    for segmento in segmentos:
        texto = segmento.texto
        correccion = correcciones_por_ubicacion.get(segmento.ubicacion)
        if correccion is not None and correccion.texto_original in texto:
            texto = texto.replace(correccion.texto_original, correccion.texto_nuevo, 1)
        documento.add_paragraph(f"[{segmento.ubicacion}] {texto}")

    buffer = io.BytesIO()
    documento.save(buffer)
    return buffer.getvalue()
