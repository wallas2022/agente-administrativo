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

Bloque K7: sin temperature=0 ni una seed fija, la respuesta del LLM no es
reproducible entre corridas -- encontrado al investigar por qué el recall de
PP-03 (CU-05) varió de 23/24 (Bloque O6) a 22/24 (Bloque K7) con el mismo
dataset, el mismo prompt y el mismo modelo: `validar_candidatos_con_llm`
(ortografia/revision.py) confirma o descarta un caso dudoso según lo que
responda el LLM, y ese muestreo era aleatorio por defecto en Ollama. Se fija
también para la redacción de hallazgos contables (RF-12): el determinismo
importa igual para la trazabilidad/auditoría (RNF-06), no solo para pruebas.
"""

import os

import httpx

# Fijos (no vienen de env): esto es determinismo de comportamiento, no
# configuración por ambiente -- local y stage deben producir la misma
# respuesta para el mismo prompt, igual que cualquier otra regla del
# validador. seed=42 no tiene significado especial, solo fija el muestreo.
TEMPERATURA_POR_DEFECTO = 0
SEMILLA_POR_DEFECTO = 42


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
            "options": {
                "temperature": TEMPERATURA_POR_DEFECTO,
                "seed": SEMILLA_POR_DEFECTO,
            },
        },
        timeout=timeout,
    )
    respuesta.raise_for_status()
    return respuesta.json()["response"]
