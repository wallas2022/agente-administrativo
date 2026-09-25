from rag.busqueda import ResultadoBusqueda
from validadores.contable.explicacion import VERSION_PROMPT, construir_prompt, generar_explicacion
from validadores.contable.reglas import HallazgoDetectado


def _hallazgo() -> HallazgoDetectado:
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


def _fragmento() -> ResultadoBusqueda:
    return ResultadoBusqueda(
        fragmento_id="politica-sec-5",
        fuente_id="politica-cierre-contable",
        contenido="## 5. Moneda\nLos registros pueden expresarse en Q o USD...",
        puntuacion=0.67,
    )


def test_construir_prompt_incluye_hallazgo_y_fuente_sin_pedir_calculos() -> None:
    prompt = construir_prompt(_hallazgo(), [_fragmento()])

    assert "RN-05" in prompt
    assert "politica-cierre-contable" in prompt
    assert "no calcules" in prompt.lower() or "no inventes" in prompt.lower()


def test_generar_explicacion_usa_la_funcion_llm_inyectada_y_versiona_el_prompt() -> None:
    prompts_recibidos = []

    def llm_falso(prompt: str) -> str:
        prompts_recibidos.append(prompt)
        return (
            "Causa probable: el comprobante registra montos en Q y USD sin indicar "
            "el tipo de cambio aplicado.\n"
            "Corrección sugerida: registrar el tipo de cambio del día en el "
            "comprobante antes de continuar (ver política de cierre, sección 5)."
        )

    explicacion = generar_explicacion(
        _hallazgo(), [_fragmento()], funcion_llm=llm_falso, modelo="qwen2.5:14b"
    )

    assert len(prompts_recibidos) == 1
    assert explicacion.version_prompt == VERSION_PROMPT
    assert explicacion.modelo_llm == "qwen2.5:14b"
    assert "tipo de cambio" in explicacion.texto.lower()
    assert explicacion.fuente_citada == "politica-cierre-contable"


def test_generar_explicacion_sin_fragmentos_no_cita_fuente() -> None:
    def llm_falso(prompt: str) -> str:
        return "Causa probable: ... Corrección sugerida: ..."

    explicacion = generar_explicacion(_hallazgo(), [], funcion_llm=llm_falso, modelo="qwen2.5:14b")

    assert explicacion.fuente_citada is None
