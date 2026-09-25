import json

from rag.busqueda import ResultadoBusqueda
from validadores.contable.explicacion import (
    VERSION_PLANTILLA,
    VERSION_PROMPT_LOTE,
    construir_prompt_lote,
    generar_explicacion_plantilla,
    generar_explicacion_plantilla_grupo,
    generar_explicaciones_lote,
)
from validadores.contable.reglas import HallazgoDetectado


def _hallazgo_rn02(fila: int = 3) -> HallazgoDetectado:
    return HallazgoDetectado(
        regla_codigo="RN-02",
        severidad="alta",
        hoja="Partidas",
        fila=fila,
        ubicacion=f"Partidas!A{fila}",
        descripcion=f"La cuenta '9999' no existe en el catálogo de cuentas vigente (fila {fila})",
    )


def _hallazgo_rn05() -> HallazgoDetectado:
    return HallazgoDetectado(
        regla_codigo="RN-05",
        severidad="alta",
        hoja="Partidas",
        fila=2,
        ubicacion="Partidas!A2",
        descripcion=(
            "El documento mezcla las monedas Q/USD sin un tipo de cambio explícito registrado"
        ),
        moneda="Q/USD",
    )


def _hallazgo_rn01() -> HallazgoDetectado:
    return HallazgoDetectado(
        regla_codigo="RN-01",
        severidad="alta",
        hoja="Partidas",
        fila=4,
        ubicacion="Partidas!A4",
        descripcion="Descuadre: total debe (900.00) no coincide con total haber (850.00)",
        monto=50.0,
    )


def _fragmento() -> ResultadoBusqueda:
    return ResultadoBusqueda(
        fragmento_id="politica-sec-5",
        fuente_id="politica-cierre-contable",
        contenido="## 5. Moneda\nLos registros pueden expresarse en Q o USD...",
        puntuacion=0.67,
    )


def test_generar_explicacion_plantilla_no_usa_llm_y_cita_la_fuente() -> None:
    explicacion = generar_explicacion_plantilla(_hallazgo_rn02(), [_fragmento()])

    assert explicacion.modelo_llm is None
    assert explicacion.version_prompt == VERSION_PLANTILLA
    assert explicacion.fuente_citada == "politica-cierre-contable"
    assert "9999" in explicacion.texto
    assert "[politica-cierre-contable]" in explicacion.texto
    assert "catálogo de cuentas" in explicacion.texto


def test_generar_explicacion_plantilla_sin_fragmentos_no_cita_fuente() -> None:
    explicacion = generar_explicacion_plantilla(_hallazgo_rn02(), [])

    assert explicacion.fuente_citada is None
    assert "[politica" not in explicacion.texto


def test_generar_explicacion_plantilla_grupo_menciona_todas_las_ubicaciones() -> None:
    hallazgos = [_hallazgo_rn02(fila=3), _hallazgo_rn02(fila=5)]
    hallazgos[1] = HallazgoDetectado(
        regla_codigo="RN-03",
        severidad="media",
        hoja="Partidas",
        fila=5,
        ubicacion="Partidas!A5",
        descripcion="La partida tiene fecha 2026-01-12, fuera del período 2026-02",
    )
    hallazgos[0] = HallazgoDetectado(
        regla_codigo="RN-03",
        severidad="media",
        hoja="Partidas",
        fila=3,
        ubicacion="Partidas!A3",
        descripcion="La partida tiene fecha 2026-01-10, fuera del período 2026-02",
    )

    explicacion = generar_explicacion_plantilla_grupo(hallazgos, [_fragmento()])

    assert "Partidas!A3" in explicacion.texto
    assert "Partidas!A5" in explicacion.texto
    assert explicacion.modelo_llm is None


def test_construir_prompt_lote_incluye_cada_hallazgo_numerado_y_pide_json() -> None:
    prompt = construir_prompt_lote([(_hallazgo_rn01(), []), (_hallazgo_rn05(), [_fragmento()])])

    assert "Hallazgo 0" in prompt
    assert "Hallazgo 1" in prompt
    assert "RN-01" in prompt
    assert "RN-05" in prompt
    assert "politica-cierre-contable" in prompt
    assert "JSON" in prompt
    assert "no calcules" in prompt.lower() or "no inventes" in prompt.lower()


def test_generar_explicaciones_lote_hace_una_sola_llamada_para_varios_hallazgos() -> None:
    prompts_recibidos = []

    def llm_falso(prompt: str) -> str:
        prompts_recibidos.append(prompt)
        return json.dumps(
            [
                {"indice": 0, "causa_probable": "causa 0", "correccion_sugerida": "correccion 0"},
                {"indice": 1, "causa_probable": "causa 1", "correccion_sugerida": "correccion 1"},
            ]
        )

    items = [(_hallazgo_rn01(), []), (_hallazgo_rn05(), [_fragmento()])]
    explicaciones = generar_explicaciones_lote(items, funcion_llm=llm_falso, modelo="gpt-oss:20b")

    assert len(prompts_recibidos) == 1  # una sola llamada, no una por hallazgo
    assert len(explicaciones) == 2
    assert "causa 0" in explicaciones[0].texto
    assert "correccion 1" in explicaciones[1].texto
    assert explicaciones[1].fuente_citada == "politica-cierre-contable"
    assert all(e.version_prompt == VERSION_PROMPT_LOTE for e in explicaciones)
    assert all(e.modelo_llm == "gpt-oss:20b" for e in explicaciones)


def test_generar_explicaciones_lote_tolera_json_envuelto_en_bloque_de_codigo() -> None:
    def llm_falso(_prompt: str) -> str:
        return (
            "Aquí está el resultado:\n```json\n"
            '[{"indice": 0, "causa_probable": "c", "correccion_sugerida": "s"}]\n'
            "```"
        )

    explicaciones = generar_explicaciones_lote(
        [(_hallazgo_rn01(), [])], funcion_llm=llm_falso, modelo="gpt-oss:20b"
    )

    assert "c" in explicaciones[0].texto


def test_generar_explicaciones_lote_usa_respaldo_si_el_json_no_es_valido() -> None:
    def llm_falso(_prompt: str) -> str:
        return "esto no es JSON en absoluto"

    explicaciones = generar_explicaciones_lote(
        [(_hallazgo_rn01(), [])], funcion_llm=llm_falso, modelo="gpt-oss:20b"
    )

    assert len(explicaciones) == 1
    assert "Descuadre" in explicaciones[0].texto  # usa hallazgo.descripcion como respaldo
    assert "revisar manualmente" in explicaciones[0].texto.lower()


def test_generar_explicaciones_lote_con_items_vacios_no_llama_al_llm() -> None:
    llamadas = []

    def llm_falso(prompt: str) -> str:
        llamadas.append(prompt)
        return "[]"

    explicaciones = generar_explicaciones_lote([], funcion_llm=llm_falso, modelo="gpt-oss:20b")

    assert explicaciones == []
    assert llamadas == []
