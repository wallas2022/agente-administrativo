import json

from ortografia.cliente_languagetool import CoincidenciaLT
from ortografia.revision import clasificar_segmentos, revisar_segmentos, validar_candidatos_con_llm
from parsers.segmentos import SegmentoTexto


def _coincidencia(
    texto: str, *, categoria: str, sugerencias: list[str] | None = None, regla_id: str = "R"
) -> CoincidenciaLT:
    return CoincidenciaLT(
        texto=texto,
        offset=0,
        longitud=len(texto),
        mensaje=f"Mensaje de {regla_id}",
        sugerencias=sugerencias or [],
        regla_id=regla_id,
        categoria=categoria,
    )


def _segmento(texto: str, ubicacion: str = "Párrafo 1") -> SegmentoTexto:
    return SegmentoTexto(texto=texto, ubicacion=ubicacion)


def _llm_no_deberia_llamarse(_prompt: str) -> str:
    raise AssertionError("no debía llamarse al LLM sin casos dudosos")


def test_coincidencia_typos_genera_hallazgo_determinista_sin_llm() -> None:
    segmento = _segmento("Este procedimiento fue aprovado por la gerencia.")

    def revisar_lt(_texto: str) -> list[CoincidenciaLT]:
        return [_coincidencia("aprovado", categoria="TYPOS", sugerencias=["aprobado", "aprobada"])]

    hallazgos = revisar_segmentos(
        [segmento],
        glosario=set(),
        funcion_revisar_lt=revisar_lt,
        funcion_llm=_llm_no_deberia_llamarse,
    )

    assert len(hallazgos) == 1
    assert hallazgos[0].ubicacion == "Párrafo 1"
    assert hallazgos[0].correccion_sugerida == "aprobado"
    assert hallazgos[0].texto_original == "aprovado"
    assert "aprovado" in hallazgos[0].descripcion
    assert hallazgos[0].regla_codigo == "RN-06"


def test_termino_de_glosario_no_genera_hallazgo() -> None:
    segmento = _segmento("La SFC aprobó el procedimiento.")

    def revisar_lt(_texto: str) -> list[CoincidenciaLT]:
        return [_coincidencia("SFC", categoria="TYPOS", sugerencias=["SIC"])]

    hallazgos = revisar_segmentos(
        [segmento],
        glosario={"SFC", "SAT", "NIIF"},
        funcion_revisar_lt=revisar_lt,
        funcion_llm=_llm_no_deberia_llamarse,
    )

    assert hallazgos == []


def test_numero_o_codigo_no_genera_hallazgo() -> None:
    segmento = _segmento("El monto es 1,250.00 quetzales")

    def revisar_lt(_texto: str) -> list[CoincidenciaLT]:
        return [_coincidencia("1,250.00", categoria="TYPOS")]

    hallazgos = revisar_segmentos(
        [segmento],
        glosario=set(),
        funcion_revisar_lt=revisar_lt,
        funcion_llm=_llm_no_deberia_llamarse,
    )

    assert hallazgos == []


def test_caso_dudoso_confirmado_por_el_llm_genera_hallazgo() -> None:
    segmento = _segmento("Es necesario que se de seguimiento al hallazgo.")

    def revisar_lt(_texto: str) -> list[CoincidenciaLT]:
        return [
            _coincidencia("de", categoria="DIACRITICS", sugerencias=["dé"], regla_id="DE_TILDE")
        ]

    def llm_falso(_prompt: str) -> str:
        return json.dumps(
            [
                {
                    "indice": 0,
                    "es_error": True,
                    "sugerencia": "dé",
                    "explicacion": "falta la tilde diacrítica",
                }
            ]
        )

    hallazgos = revisar_segmentos(
        [segmento], glosario=set(), funcion_revisar_lt=revisar_lt, funcion_llm=llm_falso
    )

    assert len(hallazgos) == 1
    assert hallazgos[0].correccion_sugerida == "dé"
    assert hallazgos[0].texto_original == "de"
    assert "diacrítica" in hallazgos[0].descripcion


def test_caso_dudoso_descartado_por_el_llm_no_genera_hallazgo() -> None:
    segmento = _segmento("El procedimiento fue aprobado a tiempo.")

    def revisar_lt(_texto: str) -> list[CoincidenciaLT]:
        return [_coincidencia("a tiempo", categoria="MISSPELLING", regla_id="A_PARTICIPIO")]

    def llm_falso(_prompt: str) -> str:
        return json.dumps([{"indice": 0, "es_error": False}])

    hallazgos = revisar_segmentos(
        [segmento], glosario=set(), funcion_revisar_lt=revisar_lt, funcion_llm=llm_falso
    )

    assert hallazgos == []


def test_varios_casos_dudosos_hacen_una_sola_llamada_al_llm() -> None:
    segmentos = [_segmento("frase uno", "Párrafo 1"), _segmento("frase dos", "Párrafo 2")]
    llamadas = []

    def revisar_lt(texto: str) -> list[CoincidenciaLT]:
        return [_coincidencia("palabra", categoria="DIACRITICS", sugerencias=["pálabra"])]

    def llm_falso(prompt: str) -> str:
        llamadas.append(prompt)
        return json.dumps(
            [
                {"indice": 0, "es_error": True, "sugerencia": "pálabra"},
                {"indice": 1, "es_error": True, "sugerencia": "pálabra"},
            ]
        )

    hallazgos = revisar_segmentos(
        segmentos, glosario=set(), funcion_revisar_lt=revisar_lt, funcion_llm=llm_falso
    )

    assert len(llamadas) == 1
    assert len(hallazgos) == 2
    assert {h.ubicacion for h in hallazgos} == {"Párrafo 1", "Párrafo 2"}


def test_respuesta_del_llm_invalida_descarta_el_caso_dudoso_sin_reventar() -> None:
    segmento = _segmento("frase con caso dudoso")

    def revisar_lt(_texto: str) -> list[CoincidenciaLT]:
        return [_coincidencia("caso", categoria="DIACRITICS")]

    def llm_falso(_prompt: str) -> str:
        return "esto no es JSON en absoluto"

    hallazgos = revisar_segmentos(
        [segmento], glosario=set(), funcion_revisar_lt=revisar_lt, funcion_llm=llm_falso
    )

    assert hallazgos == []


def test_sin_segmentos_no_llama_a_languagetool_ni_al_llm() -> None:
    llamadas_lt = []

    def revisar_lt(texto: str) -> list[CoincidenciaLT]:
        llamadas_lt.append(texto)
        return []

    hallazgos = revisar_segmentos(
        [], glosario=set(), funcion_revisar_lt=revisar_lt, funcion_llm=_llm_no_deberia_llamarse
    )

    assert hallazgos == []
    assert llamadas_lt == []


def test_clasificar_segmentos_no_llama_al_llm() -> None:
    segmento = _segmento("Es necesario que se de seguimiento al hallazgo.")

    def revisar_lt(_texto: str) -> list[CoincidenciaLT]:
        return [
            _coincidencia("de", categoria="DIACRITICS", sugerencias=["dé"], regla_id="DE_TILDE")
        ]

    resultado = clasificar_segmentos(
        [segmento], glosario=set(), funcion_revisar_lt=revisar_lt
    )

    assert resultado.deterministas == []
    assert len(resultado.dudosos) == 1
    assert resultado.dudosos[0].texto_original == "de"
    assert resultado.dudosos[0].ubicacion == "Párrafo 1"
    assert resultado.dudosos[0].sugerencia_lt == "dé"


def test_validar_candidatos_con_llm_confirma_y_descarta() -> None:
    segmento = _segmento("Es necesario que se de seguimiento al hallazgo.")

    def revisar_lt(_texto: str) -> list[CoincidenciaLT]:
        return [
            _coincidencia("de", categoria="DIACRITICS", sugerencias=["dé"], regla_id="DE_TILDE")
        ]

    clasificacion = clasificar_segmentos([segmento], glosario=set(), funcion_revisar_lt=revisar_lt)

    def llm_falso(_prompt: str) -> str:
        return json.dumps([{"indice": 0, "es_error": True, "sugerencia": "dé"}])

    resultados = validar_candidatos_con_llm(
        clasificacion.dudosos,
        contexto_por_ubicacion={segmento.ubicacion: segmento.texto},
        funcion_llm=llm_falso,
    )

    assert len(resultados) == 1
    assert resultados[0].es_error is True
    assert resultados[0].correccion_sugerida == "dé"
    assert resultados[0].candidato.texto_original == "de"


def test_mes_en_titulo_no_genera_hallazgo_ni_caso_dudoso() -> None:
    segmento = _segmento(
        "Informe de conciliación bancaria - Agosto 2026", ubicacion="Párrafo 0"
    )

    def revisar_lt(_texto: str) -> list[CoincidenciaLT]:
        return [
            _coincidencia(
                "Agosto", categoria="CASING", sugerencias=["agosto"], regla_id="MIN_MESES"
            )
        ]

    resultado = clasificar_segmentos([segmento], glosario=set(), funcion_revisar_lt=revisar_lt)

    assert resultado.deterministas == []
    assert resultado.dudosos == []


def test_mes_en_titulo_de_diapositiva_no_genera_hallazgo() -> None:
    segmento = _segmento(
        "Resultados del cierre - Agosto 2026", ubicacion="Diapositiva 1, título"
    )

    def revisar_lt(_texto: str) -> list[CoincidenciaLT]:
        return [
            _coincidencia(
                "Agosto", categoria="CASING", sugerencias=["agosto"], regla_id="MIN_MESES"
            )
        ]

    resultado = clasificar_segmentos([segmento], glosario=set(), funcion_revisar_lt=revisar_lt)

    assert resultado.deterministas == []
    assert resultado.dudosos == []


def test_mes_en_mayuscula_fuera_de_titulo_sigue_marcandose() -> None:
    segmento = _segmento(
        "El corte se hizo en Agosto según el calendario.", ubicacion="Párrafo 3"
    )

    def revisar_lt(_texto: str) -> list[CoincidenciaLT]:
        return [
            _coincidencia(
                "Agosto", categoria="CASING", sugerencias=["agosto"], regla_id="MIN_MESES"
            )
        ]

    resultado = clasificar_segmentos([segmento], glosario=set(), funcion_revisar_lt=revisar_lt)

    assert len(resultado.dudosos) == 1
    assert resultado.dudosos[0].texto_original == "Agosto"
