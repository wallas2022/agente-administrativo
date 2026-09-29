"""Bloque K6: mismo criterio que test_cliente_llm.py -- OLLAMA_KEEP_ALIVE
también aplica a los embeddings (bge-m3), que se piden con más frecuencia
que el LLM principal durante una búsqueda RAG."""

import httpx

from rag import cliente_embeddings


class _RespuestaFalsa:
    def __init__(self, cuerpo: dict) -> None:
        self._cuerpo = cuerpo

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._cuerpo


def test_obtener_embedding_envia_keep_alive_24h_por_defecto(monkeypatch) -> None:
    llamada: dict = {}

    def _post_falso(url: str, *, json: dict, timeout: float):
        llamada["json"] = json
        return _RespuestaFalsa({"embeddings": [[0.1, 0.2]]})

    monkeypatch.delenv("OLLAMA_KEEP_ALIVE", raising=False)
    monkeypatch.setattr(httpx, "post", _post_falso)

    resultado = cliente_embeddings.obtener_embedding("texto de prueba")

    assert resultado == [0.1, 0.2]
    assert llamada["json"]["keep_alive"] == "24h"


def test_obtener_embedding_respeta_ollama_keep_alive_del_entorno(monkeypatch) -> None:
    llamada: dict = {}

    def _post_falso(url: str, *, json: dict, timeout: float):
        llamada["json"] = json
        return _RespuestaFalsa({"embeddings": [[0.1, 0.2]]})

    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "10m")
    monkeypatch.setattr(httpx, "post", _post_falso)

    cliente_embeddings.obtener_embedding("texto de prueba")

    assert llamada["json"]["keep_alive"] == "10m"
