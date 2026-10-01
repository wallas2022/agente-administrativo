import json

import pytest

from validadores.redaccion.mejora import mejorar_parrafo


def _sin_coincidencias_lt(_texto: str) -> list:
    return []


def _llm_con_opciones(formal: str, breve: str):
    def _funcion(_prompt: str) -> str:
        return json.dumps(
            {
                "opciones": [
                    {"estilo": "Formal", "texto": formal, "motivos": ["más institucional"]},
                    {"estilo": "Breve", "texto": breve, "motivos": ["más corto"]},
                ]
            }
        )

    return _funcion


def test_mejora_exitosa_sin_fuente_de_estilo_aprueba_ambas_opciones() -> None:
    resultado = mejorar_parrafo(
        "hola, este es un parrafo de prueba.",
        ubicacion="Párrafo 1",
        accion="corregir",
        funcion_llm=_llm_con_opciones(
            "Hola, este es un párrafo de prueba corregido.",
            "Párrafo de prueba corregido.",
        ),
        funcion_revisar_lt=_sin_coincidencias_lt,
        glosario=set(),
    )

    assert resultado.parrafo_base == "hola, este es un parrafo de prueba."
    assert len(resultado.opciones) == 2
    assert {o.estilo for o in resultado.opciones} == {"Formal", "Breve"}
    assert all(o.aprobada_guardia for o in resultado.opciones)
    assert resultado.tiene_opciones_aprobadas is True
    assert resultado.fuente_citada is None


def test_el_parrafo_base_ya_tiene_el_formato_corregido_antes_del_llm() -> None:
    resultado = mejorar_parrafo(
        "el pago fue por Q1250 el 5/10/2026",
        ubicacion="Párrafo 1",
        accion="corregir",
        funcion_llm=_llm_con_opciones(
            "El pago fue por Q 1,250.00 el 5 de octubre de 2026, según lo acordado.",
            "Pago: Q 1,250.00, 5 de octubre de 2026.",
        ),
        funcion_revisar_lt=_sin_coincidencias_lt,
        glosario=set(),
    )

    assert resultado.parrafo_base == "el pago fue por Q 1,250.00 el 5 de octubre de 2026"


def test_la_guardia_descarta_solo_la_opcion_que_altera_un_monto() -> None:
    resultado = mejorar_parrafo(
        "el gasto fue de Q 1,250.00 segun lo revisado.",
        ubicacion="Párrafo 1",
        accion="corregir",
        funcion_llm=_llm_con_opciones(
            formal="El gasto fue de Q 1,250.00, según lo revisado.",  # cifra intacta
            breve="El gasto fue de Q 1,500.00.",  # cifra alterada
        ),
        funcion_revisar_lt=_sin_coincidencias_lt,
        glosario=set(),
    )

    assert len(resultado.opciones) == 2
    formal = next(o for o in resultado.opciones if o.estilo == "Formal")
    breve = next(o for o in resultado.opciones if o.estilo == "Breve")
    assert formal.aprobada_guardia is True
    assert breve.aprobada_guardia is False
    assert breve.razon_descarte is not None
    assert resultado.tiene_opciones_aprobadas is True


def test_ninguna_opcion_aprobada_cuando_ambas_alteran_cifras() -> None:
    resultado = mejorar_parrafo(
        "el gasto fue de Q 1,250.00.",
        ubicacion="Párrafo 1",
        accion="corregir",
        funcion_llm=_llm_con_opciones(
            formal="El gasto fue de Q 1,000.00.",
            breve="El gasto fue de Q 2,000.00.",
        ),
        funcion_revisar_lt=_sin_coincidencias_lt,
        glosario=set(),
    )

    assert resultado.tiene_opciones_aprobadas is False
    assert all(not o.aprobada_guardia for o in resultado.opciones)


def test_sin_opciones_si_el_llm_no_devuelve_json_valido() -> None:
    resultado = mejorar_parrafo(
        "hola, este es un parrafo corto.",
        ubicacion="Párrafo 1",
        accion="corregir",
        funcion_llm=lambda _prompt: "esto no es json",
        funcion_revisar_lt=_sin_coincidencias_lt,
        glosario=set(),
    )

    assert resultado.opciones == []
    assert resultado.tiene_opciones_aprobadas is False


def test_tolera_json_envuelto_en_bloque_de_codigo() -> None:
    cuerpo = json.dumps(
        {"opciones": [{"estilo": "Formal", "texto": "Texto formal.", "motivos": []}]}
    )

    def _funcion_llm(_prompt: str) -> str:
        return f"```json\n{cuerpo}\n```"

    resultado = mejorar_parrafo(
        "texto original.",
        ubicacion="Párrafo 1",
        accion="corregir",
        funcion_llm=_funcion_llm,
        funcion_revisar_lt=_sin_coincidencias_lt,
        glosario=set(),
    )

    assert len(resultado.opciones) == 1
    assert resultado.opciones[0].texto == "Texto formal."


def test_descarta_una_opcion_identica_al_parrafo_base() -> None:
    resultado = mejorar_parrafo(
        "texto original sin cambios.",
        ubicacion="Párrafo 1",
        accion="corregir",
        funcion_llm=_llm_con_opciones(
            formal="texto original sin cambios.",  # igual al base: no es una opción real
            breve="Texto breve distinto.",
        ),
        funcion_revisar_lt=_sin_coincidencias_lt,
        glosario=set(),
    )

    assert len(resultado.opciones) == 1
    assert resultado.opciones[0].estilo == "Breve"


def test_accion_invalida_lanza_value_error() -> None:
    with pytest.raises(ValueError, match="acción inválida"):
        mejorar_parrafo(
            "texto",
            ubicacion="Párrafo 1",
            accion="inventada",
            funcion_llm=lambda _p: "{}",
            funcion_revisar_lt=_sin_coincidencias_lt,
            glosario=set(),
        )
