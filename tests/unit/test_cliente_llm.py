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
