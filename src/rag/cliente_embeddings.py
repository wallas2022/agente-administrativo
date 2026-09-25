"""Cliente de embeddings vía Ollama (modelo bge-m3, RF-05/RF-16).

`LLM_BASE_URL` apunta al Ollama que corresponda al ambiente (nativo en local,
contenedor en stage — ver docs/04-pruebas/resultados/local-L1.md y
docs/03-diseno/despliegue/estrategia-ambientes.md).
"""

import os

import httpx


def obtener_embedding(
    texto: str, *, modelo: str | None = None, timeout: float = 30.0
) -> list[float]:
    base_url = os.environ.get("LLM_BASE_URL", "http://ollama:11434")
    modelo_embeddings = modelo or os.environ.get("LLM_MODEL_EMBEDDINGS", "bge-m3")
    # /api/embed (no /api/embeddings, retirado): confirmado en Ollama 0.34.4 — ver
    # docs/04-pruebas/resultados/local-S1.md.
    respuesta = httpx.post(
        f"{base_url}/api/embed",
        json={"model": modelo_embeddings, "input": texto},
        timeout=timeout,
    )
    respuesta.raise_for_status()
    return respuesta.json()["embeddings"][0]
