import pytest

from validadores.redaccion.mejora import mejorar_parrafo


def _llm_que_responde(texto: str):
    def _fn(_prompt: str) -> str:
        return texto

    return _fn


def test_mejora_exitosa_sin_fuente_de_estilo() -> None:
    llm = _llm_que_responde('{"parrafo_sugerido": "Se debe revisar el procedimiento."}')

    resultado = mejorar_parrafo(
        "Hay que revisarlo el procedimiento.",
        ubicacion="Párrafo 1",
        accion="corregir",
        funcion_llm=llm,
    )

    assert resultado.tiene_sugerencia is True
    assert resultado.parrafo_sugerido == "Se debe revisar el procedimiento."
    assert resultado.fuente_citada is None
    assert resultado.descartado_por_guardia is False


def test_sin_cambio_si_el_llm_devuelve_el_mismo_parrafo() -> None:
    original = "El procedimiento ya está bien redactado."
    llm = _llm_que_responde(f'{{"parrafo_sugerido": "{original}"}}')

    resultado = mejorar_parrafo(
        original, ubicacion="Párrafo 1", accion="corregir", funcion_llm=llm
    )

    assert resultado.tiene_sugerencia is False
    assert resultado.descartado_por_guardia is False


def test_sin_cambio_si_el_llm_no_devuelve_json_valido() -> None:
    llm = _llm_que_responde("No puedo ayudar con eso.")

    resultado = mejorar_parrafo(
        "Texto original.", ubicacion="Párrafo 1", accion="aclarar", funcion_llm=llm
    )

    assert resultado.tiene_sugerencia is False
    assert resultado.descartado_por_guardia is False


def test_la_guardia_descarta_una_sugerencia_que_altera_un_monto() -> None:
    llm = _llm_que_responde('{"parrafo_sugerido": "El gasto fue de Q 1,500.00."}')

    resultado = mejorar_parrafo(
        "El gasto fue de Q 1,250.00.",
        ubicacion="Párrafo 1",
        accion="formalizar",
        funcion_llm=llm,
    )

    assert resultado.tiene_sugerencia is False
    assert resultado.descartado_por_guardia is True
    assert "cifras" in resultado.razon_descarte.lower()
    assert resultado.parrafo_sugerido is None  # se conserva el original, no se expone


def test_tolera_json_envuelto_en_bloque_de_codigo() -> None:
    llm = _llm_que_responde(
        '```json\n{"parrafo_sugerido": "Texto mejorado."}\n```'
    )

    resultado = mejorar_parrafo(
        "Texto original.", ubicacion="Párrafo 1", accion="corregir", funcion_llm=llm
    )

    assert resultado.tiene_sugerencia is True
    assert resultado.parrafo_sugerido == "Texto mejorado."


def test_accion_invalida_lanza_value_error() -> None:
    with pytest.raises(ValueError, match="acción inválida"):
        mejorar_parrafo(
            "Texto.", ubicacion="Párrafo 1", accion="reescribir", funcion_llm=_llm_que_responde("")
        )
