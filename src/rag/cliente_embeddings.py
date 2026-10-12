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


def obtener_embedding_con_metricas(
    texto: str, *, modelo: str | None = None, timeout: float = 30.0
) -> RespuestaEmbedding:
    """Mismo comportamiento que `obtener_embedding`, pero devuelve también
    `MetricasOllama` (R-15: un embedding no genera texto, así que
    `tokens_salida`/`duracion_generacion_ms` quedan en `None` -- Ollama no
    los informa para este endpoint)."""
    base_url = os.environ.get("LLM_BASE_URL", "http://ollama:11434")
    modelo_embeddings = (
        modelo if modelo is not None else os.environ.get("LLM_MODEL_EMBEDDINGS", "bge-m3")
    )
    keep_alive = os.environ.get("OLLAMA_KEEP_ALIVE", "24h")
    # /api/embed (no /api/embeddings, retirado): confirmado en Ollama 0.34.4 — ver
    # docs/04-pruebas/resultados/local-S1.md.
    respuesta = httpx.post(
        f"{base_url}/api/embed",
        json={"model": modelo_embeddings, "input": texto, "keep_alive": keep_alive},
        timeout=timeout,
    )
    respuesta.raise_for_status()
    cuerpo_respuesta = respuesta.json()
    metricas = MetricasOllama(
        modelo=modelo_embeddings,
        tokens_entrada=cuerpo_respuesta.get("prompt_eval_count"),
        tokens_salida=None,
        duracion_total_ms=ns_a_ms(cuerpo_respuesta.get("total_duration")),
        duracion_carga_ms=ns_a_ms(cuerpo_respuesta.get("load_duration")),
        duracion_lectura_ms=ns_a_ms(cuerpo_respuesta.get("prompt_eval_duration")),
        duracion_generacion_ms=None,
    )
    return RespuestaEmbedding(vector=cuerpo_respuesta["embeddings"][0], metricas=metricas)


def obtener_embedding(
    texto: str, *, modelo: str | None = None, timeout: float = 30.0
) -> list[float]:
    resultado = obtener_embedding_con_metricas(texto, modelo=modelo, timeout=timeout)
    ULTIMAS_METRICAS_EMBEDDING.set(resultado.metricas)
    return resultado.vector
