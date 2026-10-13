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
import math
import os
import re
from collections import defaultdict
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

FRAGMENTO_MAX_TOKENS_DEFECTO = 450
FRAGMENTO_SOLAPE_TOKENS_DEFECTO = 60
# Un encabezado/pie se considera repetido si aparece en al menos 3 páginas distintas.
_MIN_PAGINAS_REPETIDO = 3
_MAX_LARGO_ENCABEZADO = 120

_CARACTERES_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u00ad]")
# Línea de índice: puntos guía (con o sin espacios) y, opcionalmente, un número de página.
_LINEA_INDICE = re.compile(r"(?:\.\s?){4,}\s*\d*\s*$")
_FIN_DE_ORACION = re.compile(r"(?<=[.!?;:])\s+")


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


def estimar_tokens(texto: str) -> int:
    """Estimación conservadora (sin tokenizador): ~3 caracteres por token, que
    sobrestima el español con bge-m3 y deja holgura bajo el batch de Ollama."""
    return math.ceil(len(texto) / 3) if texto else 0


def _entero_de_entorno(nombre: str, defecto: int) -> int:
    try:
        valor = int(os.environ.get(nombre, ""))
    except ValueError:
        return defecto
    return valor if valor > 0 else defecto


def _limpiar_texto(texto: str) -> str:
    """Quita caracteres de control y líneas de índice con puntos guía."""
    texto = _CARACTERES_CONTROL.sub("", texto)
    lineas = [ln for ln in texto.split("\n") if not _LINEA_INDICE.search(ln.rstrip())]
    return "\n".join(lineas).strip()


def _firma(texto: str) -> str:
    """Normaliza un texto para detectar repetidos entre páginas (los números varían)."""
    return re.sub(r"\d+", "#", " ".join(texto.split())).lower()


def _firmas_repetidas(segmentos: list[SegmentoTexto]) -> set[str]:
    """Textos cortos que se repiten en varias páginas distintas: encabezados y pies."""
    paginas_por_firma: dict[str, set[int]] = defaultdict(set)
    for segmento in segmentos:
        pagina = _pagina_de_ubicacion(segmento.ubicacion)
        texto = segmento.texto.strip()
        if pagina is None or not texto or len(texto) > _MAX_LARGO_ENCABEZADO:
            continue
        if _inicio_de_seccion(texto) is not None:
            continue
        paginas_por_firma[_firma(texto)].add(pagina)
    return {f for f, paginas in paginas_por_firma.items() if len(paginas) >= _MIN_PAGINAS_REPETIDO}


def _partir_por_palabras(texto: str, max_tokens: int) -> list[str]:
    max_caracteres = max(1, max_tokens * 3)
    partes: list[str] = []
    actual = ""
    for palabra in texto.split():
        while len(palabra) > max_caracteres:  # palabra enorme sin espacios
            if actual:
                partes.append(actual)
                actual = ""
            partes.append(palabra[:max_caracteres])
            palabra = palabra[max_caracteres:]
        candidata = f"{actual} {palabra}" if actual else palabra
        if len(candidata) > max_caracteres:
            partes.append(actual)
            actual = palabra
        else:
            actual = candidata
    if actual:
        partes.append(actual)
    return partes


def _unidades(parrafos: list[str], max_tokens: int) -> list[tuple[str, str]]:
    """Unidades (texto, separador previo) de a lo sumo `max_tokens`: párrafos
    completos; si uno excede el tope, por oraciones y, en último caso, por palabras."""
    unidades: list[tuple[str, str]] = []
    for parrafo in parrafos:
        if estimar_tokens(parrafo) <= max_tokens:
            unidades.append((parrafo, "\n"))
            continue
        primera = True
        for oracion in _FIN_DE_ORACION.split(parrafo):
            trozos = (
                [oracion]
                if estimar_tokens(oracion) <= max_tokens
                else _partir_por_palabras(oracion, max_tokens)
            )
            for trozo in trozos:
                unidades.append((trozo, "\n" if primera else " "))
                primera = False
    return unidades


def _cola_para_solape(unidades: list[tuple[str, str]], solape_tokens: int) -> list[tuple[str, str]]:
    """Últimas unidades que caben en el solapamiento (o el final de la última, por palabras)."""
    cola: list[tuple[str, str]] = []
    total = 0
    for unidad in reversed(unidades):
        tokens = estimar_tokens(unidad[0])
        if total + tokens > solape_tokens:
            break
        cola.insert(0, unidad)
        total += tokens
    if not cola and unidades and solape_tokens > 0:
        palabras = unidades[-1][0].split()
        seleccion: list[str] = []
        for palabra in reversed(palabras):
            if estimar_tokens(" ".join([palabra, *seleccion])) > solape_tokens:
                break
            seleccion.insert(0, palabra)
        if seleccion:
            cola = [(" ".join(seleccion), " ")]
    return cola


def _unir(unidades: list[tuple[str, str]]) -> str:
    texto = ""
    for contenido, separador in unidades:
        texto = contenido if not texto else f"{texto}{separador}{contenido}"
    return texto.strip()


def _dividir_en_fragmentos(parrafos: list[str], max_tokens: int, solape_tokens: int) -> list[str]:
    """Empaqueta párrafos en fragmentos de a lo sumo `max_tokens`, con solapamiento."""
    actuales: list[tuple[str, str]] = []
    resultado: list[str] = []
    nuevas = 0  # unidades añadidas desde el último volcado (distintas del solape)

    for unidad in _unidades(parrafos, max_tokens):
        if actuales and estimar_tokens(_unir([*actuales, unidad])) > max_tokens:
            if nuevas:
                resultado.append(_unir(actuales))
            actuales = _cola_para_solape(actuales, solape_tokens)
            nuevas = 0
            if actuales and estimar_tokens(_unir([*actuales, unidad])) > max_tokens:
                actuales = []
        actuales.append(unidad)
        nuevas += 1
    if actuales and nuevas:
        resultado.append(_unir(actuales))
    return [f for f in resultado if f]


def agrupar_por_seccion(
    segmentos: list[SegmentoTexto],
    *,
    max_tokens: int | None = None,
    solape_tokens: int | None = None,
) -> list[FragmentoExtraido]:
    """Convierte una lista plana de `SegmentoTexto` (un extractor de
    `src/parsers`) en fragmentos por sección y página, ninguno mayor que
    `FRAGMENTO_MAX_TOKENS` (450) y con solapamiento `FRAGMENTO_SOLAPE_TOKENS`
    (60) cuando una sección se divide. Quita líneas de índice con puntos
    guía, encabezados/pies repetidos y caracteres de control. Si el documento
    no tiene ninguna marca de sección/encabezado, el contenido queda con
    `seccion=None` -- sigue siendo indexable, solo que sin cita de sección."""
    tope = max_tokens or _entero_de_entorno("FRAGMENTO_MAX_TOKENS", FRAGMENTO_MAX_TOKENS_DEFECTO)
    solape = (
        solape_tokens
        if solape_tokens is not None
        else _entero_de_entorno("FRAGMENTO_SOLAPE_TOKENS", FRAGMENTO_SOLAPE_TOKENS_DEFECTO)
    )
    solape = min(solape, tope // 2)
    repetidas = _firmas_repetidas(segmentos)

    fragmentos: list[FragmentoExtraido] = []
    seccion_actual: str | None = None
    pagina_actual: int | None = None
    parrafos_actuales: list[str] = []

    def volcar() -> None:
        for contenido in _dividir_en_fragmentos(parrafos_actuales, tope, solape):
            fragmentos.append(FragmentoExtraido(contenido, seccion_actual, pagina_actual))

    for segmento in segmentos:
        pagina_segmento = _pagina_de_ubicacion(segmento.ubicacion)
        nueva_seccion = _inicio_de_seccion(segmento.texto.strip())
        if nueva_seccion is not None:
            volcar()
            seccion_actual = nueva_seccion
            pagina_actual = pagina_segmento
            parrafos_actuales = []
            continue
        if pagina_segmento is not None and _firma(segmento.texto) in repetidas:
            continue
        texto = _limpiar_texto(segmento.texto)
        if not texto:
            continue
        if (
            pagina_segmento is not None
            and pagina_actual is not None
            and pagina_segmento != pagina_actual
        ):
            volcar()
            parrafos_actuales = []
            pagina_actual = pagina_segmento
        elif pagina_actual is None:
            pagina_actual = pagina_segmento
        parrafos_actuales.append(texto)

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
    "estimar_tokens",
    "extraer_fragmentos",
]
