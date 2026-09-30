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


def test_generar_texto_envia_keep_alive_24h_por_defecto(monkeypatch) -> None:
    llamada: dict = {}

    def _post_falso(url: str, *, json: dict, timeout: float):
        llamada["json"] = json
        return _RespuestaFalsa({"response": "ok"})

    monkeypatch.delenv("OLLAMA_KEEP_ALIVE", raising=False)
    monkeypatch.setattr(httpx, "post", _post_falso)

    resultado = cliente_llm.generar_texto("hola", modelo="modelo-x")

    assert resultado == "ok"
    assert llamada["json"]["keep_alive"] == "24h"


def test_generar_texto_respeta_ollama_keep_alive_del_entorno(monkeypatch) -> None:
    llamada: dict = {}

    def _post_falso(url: str, *, json: dict, timeout: float):
        llamada["json"] = json
        return _RespuestaFalsa({"response": "ok"})

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
        return _RespuestaFalsa({"response": "ok"})

    monkeypatch.setattr(httpx, "post", _post_falso)

    cliente_llm.generar_texto("hola", modelo="modelo-x")

    assert llamada["json"]["options"]["temperature"] == 0
    assert llamada["json"]["options"]["seed"] == cliente_llm.SEMILLA_POR_DEFECTO
