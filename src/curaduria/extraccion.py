"""Extracción de fragmentos citables de una fuente de conocimiento (RF-16,
CU-08, Bloque K3): agrupa los `SegmentoTexto` de los extractores de
`src/parsers` (uno por párrafo/bloque/línea) en fragmentos más grandes, uno
por sección -- el nivel de granularidad que tiene sentido citar ("Regla
aplicada: POL-001 §3"), no un párrafo suelto.

Verificado contra los documentos reales de `kb/plantillas/ejemplos/`: tanto
el PDF (POL-001, PyMuPDF separa cada encabezado "§N ..." en su propio
bloque) como el docx (EST-001, encabezados con estilo "Heading 1" que
además empiezan con "§N") marcan sus secciones así -- de ahí que alcance
con mirar el texto completo de cada `SegmentoTexto` (no hace falta
inspeccionar el estilo del párrafo).

PDF sin texto: `parsers.pdf.leer_texto_pdf` ya lanza `PdfSinTextoError`
("requiere OCR, iteración 2") -- se deja propagar tal cual, mismo mensaje
que usa CU-05.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

from parsers.docx import leer_texto_docx
from parsers.markdown import leer_texto_md
from parsers.pdf import PdfSinTextoError, leer_texto_pdf
from parsers.segmentos import SegmentoTexto

FORMATOS_SOPORTADOS = frozenset({"docx", "pdf", "md"})

# "§3 Integridad de registros" -> "§3". También casa "§ 3" (espacio opcional).
_PATRON_SECCION = re.compile(r"^§\s*(\d+)")
# "## Título" (Markdown) -> "Título".
_PATRON_ENCABEZADO_MD = re.compile(r"^#{1,6}\s+(.+?)\s*$")
_PATRON_PAGINA_PDF = re.compile(r"^Página (\d+),")


@dataclass(frozen=True)
class FragmentoExtraido:
    """Un fragmento indexable: el contenido de una sección completa (todos
    los párrafos entre un encabezado y el siguiente), no un párrafo
    suelto. `seccion` es el token corto de cita ("§3") cuando se detectó
    una marca de sección; para Markdown sin "§N" cae al texto del
    encabezado. `pagina` solo se completa para PDF."""

    contenido: str
    seccion: str | None
    pagina: int | None


def _inicio_de_seccion(texto: str) -> str | None:
    coincidencia = _PATRON_SECCION.match(texto)
    if coincidencia:
        return f"§{coincidencia.group(1)}"
    coincidencia_md = _PATRON_ENCABEZADO_MD.match(texto)
    if coincidencia_md:
        return coincidencia_md.group(1)
    return None


def _pagina_de_ubicacion(ubicacion: str) -> int | None:
    coincidencia = _PATRON_PAGINA_PDF.match(ubicacion)
    return int(coincidencia.group(1)) if coincidencia else None


def agrupar_por_seccion(segmentos: list[SegmentoTexto]) -> list[FragmentoExtraido]:
    """Convierte una lista plana de `SegmentoTexto` (un extractor de
    `src/parsers`) en fragmentos por sección. Si el documento no tiene
    ninguna marca de sección/encabezado, todo el contenido queda como un
    único fragmento con `seccion=None` -- sigue siendo indexable, solo que
    sin cita de sección (p. ej. un memo corto de una sola idea)."""
    fragmentos: list[FragmentoExtraido] = []
    seccion_actual: str | None = None
    pagina_actual: int | None = None
    lineas_actuales: list[str] = []

    def volcar() -> None:
        contenido = "\n".join(lineas_actuales).strip()
        if contenido:
            fragmentos.append(FragmentoExtraido(contenido, seccion_actual, pagina_actual))

    for segmento in segmentos:
        pagina_segmento = _pagina_de_ubicacion(segmento.ubicacion)
        nueva_seccion = _inicio_de_seccion(segmento.texto)
        if nueva_seccion is not None:
            volcar()
            seccion_actual = nueva_seccion
            pagina_actual = pagina_segmento
            lineas_actuales = []
        else:
            if pagina_actual is None:
                pagina_actual = pagina_segmento
            lineas_actuales.append(segmento.texto)

    volcar()
    return fragmentos


def extraer_fragmentos(tipo_archivo: str, contenido: bytes) -> list[FragmentoExtraido]:
    """Punto de entrada único del Bloque K3: extensión -> extractor de
    `src/parsers` -> agrupar_por_seccion. Lanza `PdfSinTextoError` para un
    PDF escaneado (sin capa de texto) y `ValueError` para una extensión no
    soportada."""
    extension = tipo_archivo.lower().lstrip(".")
    if extension == "docx":
        segmentos = leer_texto_docx(io.BytesIO(contenido))
    elif extension == "pdf":
        segmentos = leer_texto_pdf(io.BytesIO(contenido))
    elif extension == "md":
        segmentos = leer_texto_md(contenido.decode("utf-8"))
    else:
        raise ValueError(f"Formato no soportado para ingesta de conocimiento: {tipo_archivo!r}")
    return agrupar_por_seccion(segmentos)


__all__ = [
    "FORMATOS_SOPORTADOS",
    "FragmentoExtraido",
    "PdfSinTextoError",
    "agrupar_por_seccion",
    "extraer_fragmentos",
]
