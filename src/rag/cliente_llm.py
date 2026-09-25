"""Cliente de generación de texto vía Ollama (RF-12, redacción de hallazgos).

Igual que `cliente_embeddings.py`: `LLM_BASE_URL` apunta al Ollama nativo en
local o al contenedor en stage (ver docs/04-pruebas/resultados/local-L1.md).
"""

import os

import httpx


def generar_texto(prompt: str, *, modelo: str | None = None, timeout: float = 180.0) -> str:
    base_url = os.environ.get("LLM_BASE_URL", "http://ollama:11434")
    modelo_principal = modelo or os.environ.get("LLM_MODEL_PRINCIPAL", "")
    respuesta = httpx.post(
        f"{base_url}/api/generate",
        json={"model": modelo_principal, "prompt": prompt, "stream": False},
        timeout=timeout,
    )
    respuesta.raise_for_status()
    return respuesta.json()["response"]
