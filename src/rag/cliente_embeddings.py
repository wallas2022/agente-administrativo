"""Cliente de embeddings vía Ollama (modelo bge-m3, RF-05/RF-16).

`LLM_BASE_URL` apunta al Ollama que corresponda al ambiente (nativo en local,
contenedor en stage — ver docs/04-pruebas/resultados/local-L1.md y
docs/03-diseno/despliegue/estrategia-ambientes.md).

Bloque K6: mismo "keep_alive" por request que `cliente_llm.py` -- los
embeddings se piden con más frecuencia que el LLM principal (una vez por
consulta RAG), así que evitar recargar el modelo importa más aquí.

P-13 (Bloque 1, RF-21): `obtener_embedding_con_metricas` expone las métricas
que Ollama devuelve también en `/api/embed` (duración, y tokens de entrada
si la versión de Ollama los informa) para que `comun.uso_llm` registre el
uso; `obtener_embedding` (el contrato `Callable[[str], list[float]]` que ya
usa todo el proyecto) sigue devolviendo solo el vector.
"""

import os
import time
from contextvars import ContextVar
from dataclasses import dataclass

import httpx

from rag.cliente_llm import MetricasOllama, ns_a_ms

# Confirmado contra el Ollama real (curl .../api/embed, modelo bge-m3):
# 1024 -- lo necesita curaduria.indexacion para crear la colección de Qdrant
# con el tamaño de vector correcto (Bloque K5).
DIMENSION_BGE_M3 = 1024


@dataclass(frozen=True)
class RespuestaEmbedding:
    vector: list[float]
    metricas: MetricasOllama


# P-13 (Bloque 1, RF-21): mismo motivo que ULTIMAS_METRICAS_LLM en
# cliente_llm.py -- `obtener_embedding` es Callable[[str], list[float]],
# inyectable vía Depends y sobreescribible en pruebas.
ULTIMAS_METRICAS_EMBEDDING: ContextVar[MetricasOllama | None] = ContextVar(
    "ultimas_metricas_embedding", default=None
)


@dataclass(frozen=True)
class RespuestaLoteEmbeddings:
    vectores: list[list[float]]
    metricas: MetricasOllama


EMBEDDINGS_TIMEOUT_S_DEFECTO = 300.0
EMBEDDINGS_LOTE_DEFECTO = 16
EMBEDDINGS_REINTENTOS_DEFECTO = 3
EMBEDDINGS_ESPERA_S_DEFECTO = 2.0


def _numero_de_entorno(nombre: str, defecto: float) -> float:
    try:
        valor = float(os.environ.get(nombre, ""))
    except ValueError:
        return defecto
    return valor if valor > 0 else defecto


def timeout_de_embeddings() -> float:
    """`EMBEDDINGS_TIMEOUT_S` (300 s por defecto): en CPU sin AVX y con Ollama
    ocupado un solo embedding llegó a tardar 173.8 s, así que 30 s fijos no alcanzan."""
    return _numero_de_entorno("EMBEDDINGS_TIMEOUT_S", EMBEDDINGS_TIMEOUT_S_DEFECTO)


def tamano_de_lote() -> int:
    """`EMBEDDINGS_LOTE` (16 por defecto): textos por llamada a `/api/embed`."""
    return int(_numero_de_entorno("EMBEDDINGS_LOTE", EMBEDDINGS_LOTE_DEFECTO))


def _reintentos() -> int:
    try:
        return max(0, int(os.environ.get("EMBEDDINGS_REINTENTOS", "")))
    except ValueError:
        return EMBEDDINGS_REINTENTOS_DEFECTO


def _es_reintentable(error: Exception) -> bool:
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code >= 500
    return isinstance(error, httpx.TransportError)  # timeouts, conexión rechazada o cortada


def obtener_embeddings_lote_con_metricas(
    textos: list[str], *, modelo: str | None = None, timeout: float | None = None
) -> RespuestaLoteEmbeddings:
    """Embebe varios textos en una sola llamada a `/api/embed` (`input` como
    lista). Reintenta `EMBEDDINGS_REINTENTOS` veces (3 por defecto) con espera
    creciente ante timeout, error de conexión o 5xx; un 4xx no se reintenta.
    Las métricas son las del lote completo (R-15: un embedding no genera texto,
    así que `tokens_salida`/`duracion_generacion_ms` quedan en `None`)."""
    base_url = os.environ.get("LLM_BASE_URL", "http://ollama:11434")
    modelo_embeddings = (
        modelo if modelo is not None else os.environ.get("LLM_MODEL_EMBEDDINGS", "bge-m3")
    )
    keep_alive = os.environ.get("EMBEDDINGS_KEEP_ALIVE") or os.environ.get(
        "OLLAMA_KEEP_ALIVE", "24h"
    )
    espera_s = _numero_de_entorno("EMBEDDINGS_ESPERA_S", EMBEDDINGS_ESPERA_S_DEFECTO)
    tiempo_maximo = timeout if timeout is not None else timeout_de_embeddings()
    reintentos = _reintentos()

    intento = 0
    while True:
        try:
            # /api/embed (no /api/embeddings, retirado): confirmado en Ollama 0.34.4 — ver
            # docs/04-pruebas/resultados/local-S1.md.
            respuesta = httpx.post(
                f"{base_url}/api/embed",
                json={"model": modelo_embeddings, "input": textos, "keep_alive": keep_alive},
                timeout=tiempo_maximo,
            )
            respuesta.raise_for_status()
            break
        except Exception as error:
            if intento >= reintentos or not _es_reintentable(error):
                raise
            time.sleep(espera_s * (2**intento))
            intento += 1

    cuerpo_respuesta = respuesta.json()
    vectores = cuerpo_respuesta["embeddings"]
    if len(vectores) != len(textos):
        raise ValueError(f"Ollama devolvió {len(vectores)} vectores para {len(textos)} textos")
    metricas = MetricasOllama(
        modelo=modelo_embeddings,
        tokens_entrada=cuerpo_respuesta.get("prompt_eval_count"),
        tokens_salida=None,
        duracion_total_ms=ns_a_ms(cuerpo_respuesta.get("total_duration")),
        duracion_carga_ms=ns_a_ms(cuerpo_respuesta.get("load_duration")),
        duracion_lectura_ms=ns_a_ms(cuerpo_respuesta.get("prompt_eval_duration")),
        duracion_generacion_ms=None,
    )
    return RespuestaLoteEmbeddings(vectores=vectores, metricas=metricas)


def obtener_embedding_con_metricas(
    texto: str, *, modelo: str | None = None, timeout: float | None = None
) -> RespuestaEmbedding:
    """Mismo comportamiento que `obtener_embedding`, pero devuelve también `MetricasOllama`."""
    lote = obtener_embeddings_lote_con_metricas([texto], modelo=modelo, timeout=timeout)
    return RespuestaEmbedding(vector=lote.vectores[0], metricas=lote.metricas)


def obtener_embedding(
    texto: str, *, modelo: str | None = None, timeout: float | None = None
) -> list[float]:
    resultado = obtener_embedding_con_metricas(texto, modelo=modelo, timeout=timeout)
    ULTIMAS_METRICAS_EMBEDDING.set(resultado.metricas)
    return resultado.vector


def obtener_embeddings_lote(textos: list[str]) -> list[list[float]]:
    """Contrato `Callable[[list[str]], list[list[float]]]` para indexar por lotes."""
    resultado = obtener_embeddings_lote_con_metricas(textos)
    ULTIMAS_METRICAS_EMBEDDING.set(resultado.metricas)
    return resultado.vectores
