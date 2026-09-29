"""Cliente de embeddings vía Ollama (modelo bge-m3, RF-05/RF-16).

`LLM_BASE_URL` apunta al Ollama que corresponda al ambiente (nativo en local,
contenedor en stage — ver docs/04-pruebas/resultados/local-L1.md y
docs/03-diseno/despliegue/estrategia-ambientes.md).

Bloque K6: mismo "keep_alive" por request que `cliente_llm.py` -- los
embeddings se piden con más frecuencia que el LLM principal (una vez por
consulta RAG), así que evitar recargar el modelo importa más aquí.
"""

import os

import httpx

# Confirmado contra el Ollama real (curl .../api/embed, modelo bge-m3):
# 1024 -- lo necesita curaduria.indexacion para crear la colección de Qdrant
# con el tamaño de vector correcto (Bloque K5).
DIMENSION_BGE_M3 = 1024


def obtener_embedding(
    texto: str, *, modelo: str | None = None, timeout: float = 30.0
) -> list[float]:
    base_url = os.environ.get("LLM_BASE_URL", "http://ollama:11434")
    modelo_embeddings = modelo or os.environ.get("LLM_MODEL_EMBEDDINGS", "bge-m3")
    keep_alive = os.environ.get("OLLAMA_KEEP_ALIVE", "24h")
    # /api/embed (no /api/embeddings, retirado): confirmado en Ollama 0.34.4 — ver
    # docs/04-pruebas/resultados/local-S1.md.
    respuesta = httpx.post(
        f"{base_url}/api/embed",
        json={"model": modelo_embeddings, "input": texto, "keep_alive": keep_alive},
        timeout=timeout,
    )
    respuesta.raise_for_status()
    return respuesta.json()["embeddings"][0]
