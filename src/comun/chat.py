"""Lógica del chat de la Base de Conocimiento (P-14, Bloque 2, RF-23/RF-24,
CU-12). Separado de `api/main.py` por el mismo criterio que
`comun/dashboard.py`/`comun/uso_llm.py` -- sin lógica de FastAPI acá.

RF-24: el texto de un adjunto (imagen u documento) se usa solo para esa
pregunta puntual -- nunca se indexa en Qdrant ni se guarda como
`FuenteConocimiento` (R-18, aislamiento por diseño, no por validación
posterior).
"""

from __future__ import annotations

import io

from ocr.documentos import procesar_documento
from ocr.motor import FuncionOcr
from parsers.docx import leer_texto_docx
from parsers.pdf import PdfSinTextoError, leer_texto_pdf
from parsers.xlsx import leer_texto_xlsx
from rag.busqueda import ResultadoBusqueda

EXTENSIONES_IMAGEN = frozenset({"png", "jpg", "jpeg", "tiff", "tif", "bmp"})

# Criterio de "no inventar" (RNF-03/R-17): si no hay fragmentos relevantes,
# el prompt se lo dice explícitamente a la pregunta, no solo a las
# instrucciones generales -- un modelo puede ignorar una instrucción del
# system si el contenido del mensaje la contradice implícitamente.
MENSAJE_SISTEMA = (
    "Eres el asistente del Agente Administrativo. Respondes preguntas usando "
    "unicamente los fragmentos de la Base de Conocimiento que se te dan junto "
    "con la pregunta. Si esos fragmentos no contienen informacion suficiente "
    "para responder, dilo explicitamente ('No tengo informacion sobre esto en "
    "la base de conocimiento') -- nunca inventes una respuesta ni cites una "
    "fuente que no este en los fragmentos dados."
)

SIN_FRAGMENTOS_RELEVANTES = (
    "(No se encontró ningún fragmento relevante en la base de conocimiento "
    "para esta pregunta.)"
)

# Últimos N turnos (mensajes, no preguntas) que se incluyen como contexto de
# la conversación -- acota el tamaño del prompt en conversaciones largas.
NUMERO_MAXIMO_MENSAJES_HISTORIAL = 10


class TipoArchivoNoSoportadoError(ValueError):
    pass


def extraer_texto_adjunto(
    contenido: bytes, *, nombre_archivo: str, funcion_ocr: FuncionOcr | None = None
) -> str:
    """RF-24: imagen -> OCR (`ocr.documentos.procesar_documento`, ya
    reconoce imagen suelta o PDF escaneado); docx/xlsx -> parsers
    existentes; pdf -> texto nativo primero, OCR como respaldo si no tiene
    capa de texto (`PdfSinTextoError`)."""
    extension = nombre_archivo.rsplit(".", 1)[-1].lower() if "." in nombre_archivo else ""

    if extension in EXTENSIONES_IMAGEN:
        paginas = procesar_documento(contenido, tipo_archivo=extension, funcion_ocr=funcion_ocr)
        return "\n".join(p.texto for p in paginas)
    if extension == "docx":
        return "\n".join(s.texto for s in leer_texto_docx(io.BytesIO(contenido)))
    if extension == "xlsx":
        return "\n".join(s.texto for s in leer_texto_xlsx(io.BytesIO(contenido)))
    if extension == "pdf":
        try:
            return "\n".join(s.texto for s in leer_texto_pdf(io.BytesIO(contenido)))
        except PdfSinTextoError:
            paginas = procesar_documento(contenido, tipo_archivo="pdf", funcion_ocr=funcion_ocr)
            return "\n".join(p.texto for p in paginas)

    raise TipoArchivoNoSoportadoError(
        f"Tipo de archivo no soportado para el chat: {nombre_archivo!r}"
    )


def fuentes_citadas(fragmentos: list[ResultadoBusqueda]) -> list[dict] | None:
    """Estructurado (no el texto ya formateado de `rag.busqueda.
    construir_citas`, pensado para un solo hallazgo contable) porque una
    respuesta del chat puede apoyarse en varios fragmentos a la vez. `None`
    si no hubo ningún fragmento relevante -- no una lista vacía, para que
    quien lea `Mensaje.fuentes_citadas` distinga "no citó nada" de "no se
    guardó esta información"."""
    if not fragmentos:
        return None
    return [
        {
            "fuente_id": f.fuente_id,
            "version": f.version,
            "seccion": f.seccion,
            "pagina": f.pagina,
        }
        for f in fragmentos
    ]


def _contexto_de_fragmentos(fragmentos: list[ResultadoBusqueda]) -> str:
    if not fragmentos:
        return SIN_FRAGMENTOS_RELEVANTES
    partes = []
    for f in fragmentos:
        encabezado = f"[Fuente: {f.fuente_id} v{f.version}"
        if f.seccion:
            encabezado += f", {f.seccion}"
        elif f.pagina is not None:
            encabezado += f", pág. {f.pagina}"
        encabezado += "]"
        partes.append(f"{encabezado}\n{f.contenido}")
    return "\n\n".join(partes)


def construir_mensajes(
    *,
    historial: list[tuple[str, str]],
    pregunta: str,
    fragmentos: list[ResultadoBusqueda],
    texto_adjunto: str | None = None,
) -> list[dict[str, str]]:
    """Arma la lista de mensajes para `rag.cliente_llm.generar_respuesta_chat`
    -- `historial` son los turnos ya guardados de la conversación, como
    pares `(rol, contenido)`, en orden cronológico (más viejo primero);
    solo se incluyen los últimos `NUMERO_MAXIMO_MENSAJES_HISTORIAL`."""
    mensajes: list[dict[str, str]] = [{"role": "system", "content": MENSAJE_SISTEMA}]
    for rol, contenido in historial[-NUMERO_MAXIMO_MENSAJES_HISTORIAL:]:
        mensajes.append({"role": rol, "content": contenido})

    contenido_pregunta = (
        f"Fragmentos de la base de conocimiento:\n{_contexto_de_fragmentos(fragmentos)}"
        f"\n\nPregunta: {pregunta}"
    )
    if texto_adjunto:
        contenido_pregunta += f"\n\nTexto del archivo adjunto:\n{texto_adjunto}"
    mensajes.append({"role": "user", "content": contenido_pregunta})
    return mensajes
