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
