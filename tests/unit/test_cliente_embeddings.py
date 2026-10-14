"""Bloque K6: mismo criterio que test_cliente_llm.py -- OLLAMA_KEEP_ALIVE
también aplica a los embeddings (bge-m3), que se piden con más frecuencia
que el LLM principal durante una búsqueda RAG."""

import httpx
import pytest

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


# --- P-15 Bloque 4: timeout configurable, lotes y reintentos ----------------


def _capturar_post(monkeypatch, respuestas: list) -> list[dict]:
    """Cada llamada a httpx.post consume una respuesta (o lanza la excepción dada)."""
    llamadas: list[dict] = []

    def _post(url: str, *, json: dict, timeout: float):
        llamadas.append({"json": json, "timeout": timeout})
        siguiente = respuestas.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente

    monkeypatch.setattr(httpx, "post", _post)
    return llamadas


def _ok(vectores: list[list[float]], **extra) -> _RespuestaFalsa:
    return _RespuestaFalsa({"embeddings": vectores, **extra})


def _sin_espera(monkeypatch) -> list[float]:
    esperas: list[float] = []
    monkeypatch.setattr(cliente_embeddings.time, "sleep", esperas.append)
    return esperas


def test_timeout_por_defecto_es_300_s_y_configurable(monkeypatch) -> None:
    monkeypatch.delenv("EMBEDDINGS_TIMEOUT_S", raising=False)
    llamadas = _capturar_post(monkeypatch, [_ok([[0.1]]), _ok([[0.1]])])

    cliente_embeddings.obtener_embedding("a")
    monkeypatch.setenv("EMBEDDINGS_TIMEOUT_S", "45")
    cliente_embeddings.obtener_embedding("a")

    assert [c["timeout"] for c in llamadas] == [300.0, 45.0]


def test_un_timeout_explicito_manda_sobre_el_entorno(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDINGS_TIMEOUT_S", "45")
    llamadas = _capturar_post(monkeypatch, [_ok([[0.1]])])

    cliente_embeddings.obtener_embedding("a", timeout=7)

    assert llamadas[0]["timeout"] == 7


def test_lote_envia_input_como_lista_y_devuelve_los_vectores_en_orden(monkeypatch) -> None:
    llamadas = _capturar_post(
        monkeypatch,
        [_ok([[1.0], [2.0], [3.0]], prompt_eval_count=30, total_duration=3_000_000_000)],
    )

    resultado = cliente_embeddings.obtener_embeddings_lote_con_metricas(["a", "b", "c"])

    assert llamadas[0]["json"]["input"] == ["a", "b", "c"]
    assert resultado.vectores == [[1.0], [2.0], [3.0]]
    assert resultado.metricas.tokens_entrada == 30
    assert resultado.metricas.duracion_total_ms == 3000


def test_lote_con_cantidad_distinta_de_vectores_es_un_error(monkeypatch) -> None:
    _capturar_post(monkeypatch, [_ok([[1.0]])])

    with pytest.raises(ValueError, match="2 textos"):
        cliente_embeddings.obtener_embeddings_lote_con_metricas(["a", "b"])


def test_reintenta_hasta_3_veces_con_espera_creciente(monkeypatch) -> None:
    esperas = _sin_espera(monkeypatch)
    llamadas = _capturar_post(
        monkeypatch,
        [httpx.ReadTimeout("t"), httpx.ConnectError("c"), httpx.ReadTimeout("t"), _ok([[0.5]])],
    )

    assert cliente_embeddings.obtener_embedding("a") == [0.5]

    assert len(llamadas) == 4
    assert len(esperas) == 3
    assert esperas == sorted(esperas) and esperas[0] < esperas[-1]


def test_agotados_los_reintentos_propaga_el_timeout(monkeypatch) -> None:
    _sin_espera(monkeypatch)
    llamadas = _capturar_post(monkeypatch, [httpx.ReadTimeout("t")] * 4)

    with pytest.raises(httpx.ReadTimeout):
        cliente_embeddings.obtener_embedding("a")

    assert len(llamadas) == 4


class _RespuestaConEstado:
    def __init__(self, codigo: int) -> None:
        request = httpx.Request("POST", "http://ollama/api/embed")
        self._r = httpx.Response(codigo, request=request)

    def raise_for_status(self) -> None:
        self._r.raise_for_status()

    def json(self) -> dict:
        return {"embeddings": [[0.9]]}


def test_error_5xx_se_reintenta_y_4xx_no(monkeypatch) -> None:
    _sin_espera(monkeypatch)
    llamadas = _capturar_post(monkeypatch, [_RespuestaConEstado(503), _ok([[0.2]])])
    assert cliente_embeddings.obtener_embedding("a") == [0.2]
    assert len(llamadas) == 2

    llamadas = _capturar_post(monkeypatch, [_RespuestaConEstado(400), _ok([[0.2]])])
    with pytest.raises(httpx.HTTPStatusError):
        cliente_embeddings.obtener_embedding("a")
    assert len(llamadas) == 1


def test_los_reintentos_son_configurables(monkeypatch) -> None:
    _sin_espera(monkeypatch)
    monkeypatch.setenv("EMBEDDINGS_REINTENTOS", "1")
    llamadas = _capturar_post(monkeypatch, [httpx.ReadTimeout("t")] * 4)

    with pytest.raises(httpx.ReadTimeout):
        cliente_embeddings.obtener_embedding("a")

    assert len(llamadas) == 2


def test_keep_alive_de_embeddings_tiene_su_propia_variable(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "10m")
    monkeypatch.setenv("EMBEDDINGS_KEEP_ALIVE", "1h")
    llamadas = _capturar_post(monkeypatch, [_ok([[0.1]])])

    cliente_embeddings.obtener_embedding("a")

    assert llamadas[0]["json"]["keep_alive"] == "1h"


def test_tamano_de_lote_por_defecto_16_y_configurable(monkeypatch) -> None:
    monkeypatch.delenv("EMBEDDINGS_LOTE", raising=False)
    assert cliente_embeddings.tamano_de_lote() == 16
    monkeypatch.setenv("EMBEDDINGS_LOTE", "4")
    assert cliente_embeddings.tamano_de_lote() == 4
    monkeypatch.setenv("EMBEDDINGS_LOTE", "basura")
    assert cliente_embeddings.tamano_de_lote() == 16
