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


# --- obtener_embedding_con_metricas (P-13, Bloque 1, RF-21) ----------------


def test_obtener_embedding_con_metricas_expone_duraciones(monkeypatch) -> None:
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, *, json, timeout: _RespuestaFalsa(
            {
                "embeddings": [[0.1, 0.2]],
                "prompt_eval_count": 8,
                "total_duration": 2_000_000_000,
                "load_duration": 500_000_000,
            }
        ),
    )

    resultado = cliente_embeddings.obtener_embedding_con_metricas("texto", modelo="bge-m3")

    assert resultado.vector == [0.1, 0.2]
    assert resultado.metricas.modelo == "bge-m3"
    assert resultado.metricas.tokens_entrada == 8
    assert resultado.metricas.tokens_salida is None
    assert resultado.metricas.duracion_total_ms == 2000
    assert resultado.metricas.duracion_carga_ms == 500
    assert resultado.metricas.duracion_generacion_ms is None


def test_obtener_embedding_sigue_devolviendo_solo_el_vector(monkeypatch) -> None:
    monkeypatch.setattr(
        httpx, "post", lambda url, *, json, timeout: _RespuestaFalsa({"embeddings": [[0.3, 0.4]]})
    )

    resultado = cliente_embeddings.obtener_embedding("texto")

    assert resultado == [0.3, 0.4]
