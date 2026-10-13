"""P-14 (Bloque 2, RF-23/RF-24, CU-12): lógica pura del chat de la Base de
Conocimiento -- extracción de texto de un adjunto (dispatch por extensión,
sin repetir las pruebas de los parsers/OCR ya existentes) y armado de los
mensajes para el LLM.
"""

import pytest

from comun import chat
from ocr.modelos import Linea, Palabra, ResultadoPagina
from parsers.pdf import PdfSinTextoError
from parsers.segmentos import SegmentoTexto
from rag.busqueda import ResultadoBusqueda


def _pagina(texto: str) -> ResultadoPagina:
    palabra = Palabra(texto=texto, izquierda=0, arriba=0, ancho=10, alto=10, confianza=90.0)
    linea = Linea(texto=texto, palabras=(palabra,))
    return ResultadoPagina(
        numero=1,
        ancho_px=100,
        alto_px=100,
        lineas=(linea,),
        palabras=(palabra,),
        confianza_media=90.0,
    )


def _fragmento(
    *, fuente_id="POL-001", version="2026-01", seccion="§3", pagina=None, contenido="texto"
) -> ResultadoBusqueda:
    return ResultadoBusqueda(
        fragmento_id="f1",
        fuente_id=fuente_id,
        contenido=contenido,
        puntuacion=0.9,
        prioridad=1,
        tipo="regla_interna",
        version=version,
        seccion=seccion,
        pagina=pagina,
    )


# --- extraer_texto_adjunto ---------------------------------------------------


def test_extraer_texto_adjunto_imagen_usa_ocr(monkeypatch) -> None:
    llamada = {}

    def _procesar_documento_falso(contenido, *, tipo_archivo, funcion_ocr=None):
        llamada["tipo_archivo"] = tipo_archivo
        return [_pagina("línea reconocida")]

    monkeypatch.setattr(chat, "procesar_documento", _procesar_documento_falso)

    texto = chat.extraer_texto_adjunto(b"bytes", nombre_archivo="foto.png")

    assert llamada["tipo_archivo"] == "png"
    assert texto == "línea reconocida"


def test_extraer_texto_adjunto_docx_usa_el_parser_de_docx(monkeypatch) -> None:
    monkeypatch.setattr(
        chat, "leer_texto_docx", lambda archivo: [SegmentoTexto(texto="párrafo 1", ubicacion="p0")]
    )

    texto = chat.extraer_texto_adjunto(b"bytes", nombre_archivo="memo.docx")

    assert texto == "párrafo 1"


def test_extraer_texto_adjunto_xlsx_usa_el_parser_de_xlsx(monkeypatch) -> None:
    monkeypatch.setattr(
        chat,
        "leer_texto_xlsx",
        lambda archivo: [SegmentoTexto(texto="A1: hola", ubicacion="Hoja1!A1")],
    )

    texto = chat.extraer_texto_adjunto(b"bytes", nombre_archivo="datos.xlsx")

    assert texto == "A1: hola"


def test_extraer_texto_adjunto_pdf_con_texto_nativo_no_usa_ocr(monkeypatch) -> None:
    monkeypatch.setattr(
        chat,
        "leer_texto_pdf",
        lambda archivo: [SegmentoTexto(texto="texto del pdf", ubicacion="p1")],
    )

    def _procesar_documento_que_no_deberia_llamarse(*args, **kwargs):
        raise AssertionError("no debería llamar a OCR si el PDF tiene texto nativo")

    monkeypatch.setattr(chat, "procesar_documento", _procesar_documento_que_no_deberia_llamarse)

    texto = chat.extraer_texto_adjunto(b"bytes", nombre_archivo="informe.pdf")

    assert texto == "texto del pdf"


def test_extraer_texto_adjunto_pdf_escaneado_cae_a_ocr(monkeypatch) -> None:
    def _leer_texto_pdf_que_falla(archivo):
        raise PdfSinTextoError("sin capa de texto")

    llamada = {}

    def _procesar_documento_falso(contenido, *, tipo_archivo, funcion_ocr=None):
        llamada["tipo_archivo"] = tipo_archivo
        return [_pagina("texto ocr del pdf escaneado")]

    monkeypatch.setattr(chat, "leer_texto_pdf", _leer_texto_pdf_que_falla)
    monkeypatch.setattr(chat, "procesar_documento", _procesar_documento_falso)

    texto = chat.extraer_texto_adjunto(b"bytes", nombre_archivo="escaneado.pdf")

    assert llamada["tipo_archivo"] == "pdf"
    assert texto == "texto ocr del pdf escaneado"


def test_extraer_texto_adjunto_tipo_no_soportado_lanza_error() -> None:
    with pytest.raises(chat.TipoArchivoNoSoportadoError):
        chat.extraer_texto_adjunto(b"bytes", nombre_archivo="presentacion.pptx")


# --- fuentes_citadas ----------------------------------------------------------


def test_fuentes_citadas_vacio_es_none_no_lista_vacia() -> None:
    assert chat.fuentes_citadas([]) is None


def test_fuentes_citadas_devuelve_los_campos_relevantes_de_cada_fragmento() -> None:
    fragmentos = [_fragmento(fuente_id="POL-001", version="2026-01", seccion="§3")]

    resultado = chat.fuentes_citadas(fragmentos)

    assert resultado == [
        {"fuente_id": "POL-001", "version": "2026-01", "seccion": "§3", "pagina": None}
    ]


# --- construir_mensajes -------------------------------------------------------


def test_construir_mensajes_sin_fragmentos_marca_explicitamente_que_no_hay_informacion() -> None:
    mensajes = chat.construir_mensajes(historial=[], pregunta="¿algo?", fragmentos=[])

    assert mensajes[0] == {"role": "system", "content": chat.MENSAJE_SISTEMA}
    assert "No se encontró ningún fragmento relevante" in mensajes[-1]["content"]
    assert "¿algo?" in mensajes[-1]["content"]


def test_construir_mensajes_incluye_el_contenido_de_los_fragmentos() -> None:
    fragmentos = [_fragmento(contenido="el límite diario es Q300")]

    mensajes = chat.construir_mensajes(
        historial=[], pregunta="¿cuál es el límite?", fragmentos=fragmentos
    )

    assert "el límite diario es Q300" in mensajes[-1]["content"]
    assert "POL-001" in mensajes[-1]["content"]


def test_construir_mensajes_incluye_el_historial_en_orden(monkeypatch) -> None:
    historial = [("user", "primera pregunta"), ("assistant", "primera respuesta")]

    mensajes = chat.construir_mensajes(
        historial=historial, pregunta="segunda pregunta", fragmentos=[]
    )

    assert mensajes[1] == {"role": "user", "content": "primera pregunta"}
    assert mensajes[2] == {"role": "assistant", "content": "primera respuesta"}
    assert mensajes[-1]["role"] == "user"
    assert "segunda pregunta" in mensajes[-1]["content"]


def test_construir_mensajes_recorta_el_historial_a_los_ultimos_n_mensajes() -> None:
    historial = [("user", f"mensaje {i}") for i in range(chat.NUMERO_MAXIMO_MENSAJES_HISTORIAL + 5)]

    mensajes = chat.construir_mensajes(historial=historial, pregunta="actual", fragmentos=[])

    # system + los últimos N del historial + el mensaje actual.
    assert len(mensajes) == 1 + chat.NUMERO_MAXIMO_MENSAJES_HISTORIAL + 1
    assert mensajes[1]["content"] == "mensaje 5"


def test_construir_mensajes_agrega_el_texto_del_adjunto() -> None:
    mensajes = chat.construir_mensajes(
        historial=[], pregunta="¿qué dice?", fragmentos=[], texto_adjunto="contenido del archivo"
    )

    assert "contenido del archivo" in mensajes[-1]["content"]
