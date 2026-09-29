"""Cliente de generación de texto vía Ollama (RF-12, redacción de hallazgos).

Igual que `cliente_embeddings.py`: `LLM_BASE_URL` apunta al Ollama nativo en
local o al contenedor en stage (ver docs/04-pruebas/resultados/local-L1.md).

Timeout por defecto de 300s: `gpt-oss:20b` (modelo por defecto desde 2026-09-25,
ver docs/04-pruebas/resultados/local-S1.md) tardó hasta ~224s en una sola
llamada en el hardware sin GPU de esta máquina — 180s no daba margen suficiente.

Bloque K6: se manda "keep_alive" en cada request (no basta con la variable de
entorno OLLAMA_KEEP_ALIVE del lado servidor -- el Ollama nativo de Windows no
lee el `.env.local` de Docker, ver docs/06-operacion/instalacion.md) para
evitar recargar el modelo entre llamadas.
"""

import os

import httpx


def generar_texto(prompt: str, *, modelo: str | None = None, timeout: float = 300.0) -> str:
    base_url = os.environ.get("LLM_BASE_URL", "http://ollama:11434")
    modelo_principal = modelo or os.environ.get("LLM_MODEL_PRINCIPAL", "")
    keep_alive = os.environ.get("OLLAMA_KEEP_ALIVE", "24h")
    respuesta = httpx.post(
        f"{base_url}/api/generate",
        json={
            "model": modelo_principal,
            "prompt": prompt,
            "stream": False,
            "keep_alive": keep_alive,
        },
        timeout=timeout,
    )
    respuesta.raise_for_status()
    return respuesta.json()["response"]
