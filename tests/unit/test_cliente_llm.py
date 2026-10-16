"""Bloque K6: OLLAMA_KEEP_ALIVE=24h documentado no basta por sí solo -- el
Ollama nativo de Windows no lee el `.env.local` de Docker (ver
docs/06-operacion/instalacion.md), así que `generar_texto` manda
"keep_alive" en cada request para que el modelo quede cargado sin depender
de esa variable en el servidor.
"""

import httpx

from rag import cliente_llm


class _RespuestaFalsa:
    def __init__(self, cuerpo: dict) -> None:
        self._cuerpo = cuerpo

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._cuerpo


def _respuesta_de_chat(contenido: str = "ok") -> _RespuestaFalsa:
    return _RespuestaFalsa({"message": {"content": contenido}})


def _respuesta_de_chat_con_metricas(contenido: str = "ok") -> _RespuestaFalsa:
    return _RespuestaFalsa(
        {
            "message": {"content": contenido},
            "prompt_eval_count": 120,
            "eval_count": 45,
            "total_duration": 5_000_000_000,
            "load_duration": 1_000_000_000,
            "prompt_eval_duration": 500_000_000,
            "eval_duration": 3_500_000_000,
        }
    )


def test_generar_texto_envia_keep_alive_24h_por_defecto(monkeypatch) -> None:
    llamada: dict = {}

    def _post_falso(url: str, *, json: dict, timeout: float):
        llamada["json"] = json
        return _respuesta_de_chat()

    monkeypatch.delenv("OLLAMA_KEEP_ALIVE", raising=False)
    monkeypatch.setattr(httpx, "post", _post_falso)

    resultado = cliente_llm.generar_texto("hola", modelo="modelo-x")

    assert resultado == "ok"
    assert llamada["json"]["keep_alive"] == "24h"


def test_generar_texto_respeta_ollama_keep_alive_del_entorno(monkeypatch) -> None:
    llamada: dict = {}

    def _post_falso(url: str, *, json: dict, timeout: float):
        llamada["json"] = json
        return _respuesta_de_chat()

    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "10m")
    monkeypatch.setattr(httpx, "post", _post_falso)

    cliente_llm.generar_texto("hola", modelo="modelo-x")

    assert llamada["json"]["keep_alive"] == "10m"


def test_generar_texto_envia_temperature_0_y_seed_fija_por_defecto(monkeypatch) -> None:
    """Hallazgo O6->K7 (PP-03, CU-05): sin temperature=0 ni seed fija, la
    validación de casos dudosos por LLM (ortografia.revision.
    validar_candidatos_con_llm) no es reproducible entre corridas -- el
    recall de PP-03 varió de 23/24 (O6) a 22/24 (K7) con el mismo dataset y
    el mismo prompt, solo por el muestreo aleatorio de Ollama. Mismo
    criterio para la redacción de hallazgos contables (RF-12): determinismo
    también importa para la trazabilidad/auditoría (RNF-06)."""
    llamada: dict = {}

    def _post_falso(url: str, *, json: dict, timeout: float):
        llamada["json"] = json
        return _respuesta_de_chat()

    monkeypatch.setattr(httpx, "post", _post_falso)

    cliente_llm.generar_texto("hola", modelo="modelo-x")

    assert llamada["json"]["options"]["temperature"] == 0
    assert llamada["json"]["options"]["seed"] == cliente_llm.SEMILLA_POR_DEFECTO


def test_generar_texto_manda_el_prompt_como_mensaje_de_usuario(monkeypatch) -> None:
    """CU-02 (optimización de rendimiento): se usa /api/chat, no
    /api/generate -- medido contra gpt-oss:20b real, `think` funciona de
    forma confiable solo por /api/chat (ver cliente_llm.py)."""
    llamada: dict = {}

    def _post_falso(url: str, *, json: dict, timeout: float):
        llamada["url"] = url
        llamada["json"] = json
        return _respuesta_de_chat()

    monkeypatch.setattr(httpx, "post", _post_falso)

    cliente_llm.generar_texto("hola", modelo="modelo-x")

    assert llamada["url"].endswith("/api/chat")
    assert llamada["json"]["messages"] == [{"role": "user", "content": "hola"}]


def test_generar_texto_sin_formato_no_manda_el_campo_format(monkeypatch) -> None:
    llamada: dict = {}

    def _post_falso(url: str, *, json: dict, timeout: float):
        llamada["json"] = json
        return _respuesta_de_chat()

    monkeypatch.setattr(httpx, "post", _post_falso)

    cliente_llm.generar_texto("hola", modelo="modelo-x")

    assert "format" not in llamada["json"]


def test_generar_texto_formato_json_activa_salida_estructurada_de_ollama(monkeypatch) -> None:
    llamada: dict = {}

    def _post_falso(url: str, *, json: dict, timeout: float):
        llamada["json"] = json
        return _respuesta_de_chat()

    monkeypatch.setattr(httpx, "post", _post_falso)

    cliente_llm.generar_texto("hola", modelo="modelo-x", formato="json")

    assert llamada["json"]["format"] == "json"


def test_generar_texto_acepta_un_esquema_json_como_formato(monkeypatch) -> None:
    """Medido contra gpt-oss:20b real: format="json" a secas deja que el
    modelo deforme la estructura esperada (p. ej. mete una opción dentro de
    otra); un esquema JSON explícito sí produce la forma correcta."""
    llamada: dict = {}
    esquema = {"type": "object", "properties": {"x": {"type": "string"}}}

    def _post_falso(url: str, *, json: dict, timeout: float):
        llamada["json"] = json
        return _respuesta_de_chat()

    monkeypatch.setattr(httpx, "post", _post_falso)

    cliente_llm.generar_texto("hola", modelo="modelo-x", formato=esquema)

    assert llamada["json"]["format"] == esquema


def test_generar_texto_sin_pensamiento_no_manda_el_campo_think(monkeypatch) -> None:
    llamada: dict = {}

    def _post_falso(url: str, *, json: dict, timeout: float):
        llamada["json"] = json
        return _respuesta_de_chat()

    monkeypatch.setattr(httpx, "post", _post_falso)

    cliente_llm.generar_texto("hola", modelo="modelo-x")

    assert "think" not in llamada["json"]


def test_generar_texto_pensamiento_low_reduce_el_esfuerzo_de_razonamiento(monkeypatch) -> None:
    """CU-02 (RF-07, rendimiento): medido contra gpt-oss:20b real,
    think="low" bajó el campo "thinking" de la respuesta de ~1716 a ~585
    caracteres en el mismo párrafo -- ver
    docs/04-pruebas/resultados/local-cu02-rendimiento.md."""
    llamada: dict = {}

    def _post_falso(url: str, *, json: dict, timeout: float):
        llamada["json"] = json
        return _respuesta_de_chat()

    monkeypatch.setattr(httpx, "post", _post_falso)

    cliente_llm.generar_texto("hola", modelo="modelo-x", pensamiento="low")

    assert llamada["json"]["think"] == "low"


def test_generar_texto_num_ctx_y_num_predict_van_dentro_de_options(monkeypatch) -> None:
    llamada: dict = {}

    def _post_falso(url: str, *, json: dict, timeout: float):
        llamada["json"] = json
        return _respuesta_de_chat()

    monkeypatch.setattr(httpx, "post", _post_falso)

    cliente_llm.generar_texto("hola", modelo="modelo-x", num_ctx=2048, num_predict=400)

    assert llamada["json"]["options"]["num_ctx"] == 2048
    assert llamada["json"]["options"]["num_predict"] == 400


def test_generar_texto_devuelve_el_contenido_del_mensaje(monkeypatch) -> None:
    def _post_falso(url: str, *, json: dict, timeout: float):
        return _respuesta_de_chat("el párrafo mejorado")

    monkeypatch.setattr(httpx, "post", _post_falso)

    resultado = cliente_llm.generar_texto("hola", modelo="modelo-x")

    assert resultado == "el párrafo mejorado"


# --- generar_texto_con_metricas (P-13, Bloque 1, RF-21) --------------------


def test_generar_texto_con_metricas_expone_tokens_y_duraciones(monkeypatch) -> None:
    monkeypatch.setattr(
        httpx, "post", lambda url, *, json, timeout: _respuesta_de_chat_con_metricas()
    )

    resultado = cliente_llm.generar_texto_con_metricas("hola", modelo="modelo-x")

    assert resultado.texto == "ok"
    assert resultado.metricas.modelo == "modelo-x"
    assert resultado.metricas.tokens_entrada == 120
    assert resultado.metricas.tokens_salida == 45
    assert resultado.metricas.duracion_total_ms == 5000
    assert resultado.metricas.duracion_carga_ms == 1000
    assert resultado.metricas.duracion_lectura_ms == 500
    assert resultado.metricas.duracion_generacion_ms == 3500


def test_generar_texto_con_metricas_usa_none_si_ollama_no_informa_un_campo(monkeypatch) -> None:
    """R-15: una versión de Ollama que no informa un campo no debe hacer
    fallar el registro de uso -- se guarda None, nunca se estima."""
    monkeypatch.setattr(
        httpx, "post", lambda url, *, json, timeout: _respuesta_de_chat("ok")
    )

    resultado = cliente_llm.generar_texto_con_metricas("hola", modelo="modelo-x")

    assert resultado.metricas.tokens_entrada is None
    assert resultado.metricas.tokens_salida is None
    assert resultado.metricas.duracion_total_ms is None


def test_generar_texto_sigue_devolviendo_solo_el_texto(monkeypatch) -> None:
    """generar_texto (Callable[[str], str]) es el contrato que ya usa todo
    el proyecto -- no debe cambiar aunque generar_texto_con_metricas exista."""
    monkeypatch.setattr(
        httpx, "post", lambda url, *, json, timeout: _respuesta_de_chat_con_metricas("hola")
    )

    resultado = cliente_llm.generar_texto("hola", modelo="modelo-x")

    assert resultado == "hola"
    assert isinstance(resultado, str)


def test_ns_a_ms_convierte_nanosegundos_a_milisegundos() -> None:
    assert cliente_llm.ns_a_ms(5_000_000_000) == 5000
    assert cliente_llm.ns_a_ms(None) is None


# --- generar_respuesta_chat (P-14, Bloque 1, RF-23) ------------------------


def test_generar_respuesta_chat_manda_el_historial_completo(monkeypatch) -> None:
    llamada: dict = {}
    historial = [
        {"role": "system", "content": "Responde solo con la base de conocimiento."},
        {"role": "user", "content": "¿Qué dice la política de viáticos?"},
        {"role": "assistant", "content": "Según POL-001 §3, el límite diario es Q300."},
        {"role": "user", "content": "¿Y para viajes internacionales?"},
    ]

    def _post_falso(url: str, *, json: dict, timeout: float):
        llamada["url"] = url
        llamada["json"] = json
        return _respuesta_de_chat("Para viajes internacionales, ver POL-001 §4.")

    monkeypatch.setattr(httpx, "post", _post_falso)

    resultado = cliente_llm.generar_respuesta_chat(historial, modelo="modelo-x")

    assert llamada["url"].endswith("/api/chat")
    assert llamada["json"]["messages"] == historial
    assert resultado.texto == "Para viajes internacionales, ver POL-001 §4."


def test_generar_respuesta_chat_expone_metricas_igual_que_generar_texto_con_metricas(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        httpx, "post", lambda url, *, json, timeout: _respuesta_de_chat_con_metricas()
    )

    resultado = cliente_llm.generar_respuesta_chat(
        [{"role": "user", "content": "hola"}], modelo="modelo-x"
    )

    assert resultado.metricas.modelo == "modelo-x"
    assert resultado.metricas.tokens_entrada == 120
    assert resultado.metricas.tokens_salida == 45


def test_generar_respuesta_chat_no_manda_formato_ni_pensamiento(monkeypatch) -> None:
    llamada: dict = {}

    def _post_falso(url: str, *, json: dict, timeout: float):
        llamada["json"] = json
        return _respuesta_de_chat()

    monkeypatch.setattr(httpx, "post", _post_falso)

    cliente_llm.generar_respuesta_chat([{"role": "user", "content": "hola"}], modelo="modelo-x")

    assert "format" not in llamada["json"]
    assert "think" not in llamada["json"]


def test_generar_respuesta_chat_respeta_keep_alive_y_temperatura_fija(monkeypatch) -> None:
    llamada: dict = {}

    def _post_falso(url: str, *, json: dict, timeout: float):
        llamada["json"] = json
        return _respuesta_de_chat()

    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "10m")
    monkeypatch.setattr(httpx, "post", _post_falso)

    cliente_llm.generar_respuesta_chat([{"role": "user", "content": "hola"}], modelo="modelo-x")

    assert llamada["json"]["keep_alive"] == "10m"
    assert llamada["json"]["options"]["temperature"] == 0
    assert llamada["json"]["options"]["seed"] == cliente_llm.SEMILLA_POR_DEFECTO


def test_generar_respuesta_chat_acepta_pensamiento_y_limites_de_contexto(monkeypatch) -> None:
    """Medido en vivo contra gpt-oss:20b real (ver api/main.py,
    enviar_mensaje_chat): sin acotar pensamiento/num_predict, un prompt de
    chat superó el timeout de 300s -- mismo ajuste que ya usa CU-02."""
    llamada: dict = {}

    def _post_falso(url: str, *, json: dict, timeout: float):
        llamada["json"] = json
        return _respuesta_de_chat()

    monkeypatch.setattr(httpx, "post", _post_falso)

    cliente_llm.generar_respuesta_chat(
        [{"role": "user", "content": "hola"}],
        modelo="modelo-x",
        pensamiento="low",
        num_ctx=4096,
        num_predict=800,
    )

    assert llamada["json"]["think"] == "low"
    assert llamada["json"]["options"]["num_ctx"] == 4096
    assert llamada["json"]["options"]["num_predict"] == 800


def test_el_timeout_del_llm_es_300_s_y_se_configura_por_entorno(monkeypatch) -> None:
    vistos: list[float] = []

    def _post(url: str, *, json: dict, timeout: float):
        vistos.append(timeout)
        return _RespuestaFalsa({"message": {"content": "ok"}})

    monkeypatch.setattr(httpx, "post", _post)
    monkeypatch.delenv("LLM_TIMEOUT_S", raising=False)
    cliente_llm.generar_texto("hola")
    monkeypatch.setenv("LLM_TIMEOUT_S", "600")
    cliente_llm.generar_texto("hola")
    monkeypatch.setenv("LLM_TIMEOUT_S", "no-es-numero")
    cliente_llm.generar_texto("hola")
    cliente_llm.generar_texto("hola", timeout=7)

    assert vistos == [300.0, 600.0, 300.0, 7]
