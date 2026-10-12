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

CU-02 (optimización de tiempo, 2026-10-01): se cambió de `/api/generate` a
`/api/chat` -- medido contra gpt-oss:20b real: con `/api/generate`,
`think="low"` no bajaba el tiempo de forma confiable (una corrida dio 185s,
con una respuesta JSON deformada); con `/api/chat`, la misma opción sí
recorta el razonamiento de verdad (de ~1716 a ~585 caracteres de
"thinking") y además cachea el prompt mucho mejor (prompt_eval_duration de
~38s a ~1-2s). Ver docs/04-pruebas/resultados/local-cu02-rendimiento.md.

P-13 (Bloque 1, RF-21): Ollama ya devuelve tokens y duraciones en cada
respuesta de `/api/chat` -- `generar_texto_con_metricas` las expone para que
`comun.uso_llm` las registre; `generar_texto` (el contrato que ya usa todo
el proyecto, `Callable[[str], str]`) sigue devolviendo solo el texto, sin
romper a ningún llamador existente.
"""

import os
from contextvars import ContextVar
from dataclasses import dataclass

import httpx

# Fijos (no vienen de env): esto es determinismo de comportamiento, no
# configuración por ambiente -- local y stage deben producir la misma
# respuesta para el mismo prompt, igual que cualquier otra regla del
# validador. seed=42 no tiene significado especial, solo fija el muestreo.
TEMPERATURA_POR_DEFECTO = 0
SEMILLA_POR_DEFECTO = 42


@dataclass(frozen=True)
class MetricasOllama:
    """P-13 (RF-21): lo que Ollama reporta de una llamada real -- cualquier
    campo puede venir ausente según la versión de Ollama o el tipo de
    llamada (los embeddings no generan texto, por ejemplo); `comun.uso_llm`
    registra `None` en vez de inventar un valor (R-15)."""

    modelo: str
    tokens_entrada: int | None
    tokens_salida: int | None
    duracion_total_ms: int | None
    duracion_carga_ms: int | None
    duracion_lectura_ms: int | None
    duracion_generacion_ms: int | None


@dataclass(frozen=True)
class RespuestaTexto:
    texto: str
    metricas: MetricasOllama


# P-13 (Bloque 1, RF-21): `generar_texto` (el Callable[[str], str] que usan
# api/main.py y orquestador/tareas.py, también inyectable vía Depends y
# sobreescribible en pruebas con un fake) no puede devolver las métricas sin
# cambiar su firma -- quien quiera registrarlas sin tocar el valor de
# retorno (`comun.uso_llm`, envolviendo un Callable ya construido/inyectado)
# las lee de acá justo después de llamarlo. `ContextVar` (no una variable de
# módulo simple) para que sea seguro entre llamadas concurrentes. Un fake de
# prueba que no pasa por `generar_texto` simplemente no lo toca -- quien lee
# el contextvar lo resetea a `None` antes de cada llamada para no leer un
# valor obsoleto de una llamada previa.
ULTIMAS_METRICAS_LLM: ContextVar[MetricasOllama | None] = ContextVar(
    "ultimas_metricas_llm", default=None
)


def ns_a_ms(valor: object) -> int | None:
    """Ollama reporta duraciones en nanosegundos; `uso_llm` las guarda en
    milisegundos -- compartida con `cliente_embeddings.py` para no duplicar
    la conversión."""
    return int(valor) // 1_000_000 if isinstance(valor, int | float) else None


def generar_texto_con_metricas(
    prompt: str,
    *,
    modelo: str | None = None,
    timeout: float = 300.0,
    formato: str | dict | None = None,
    pensamiento: str | None = None,
    num_ctx: int | None = None,
    num_predict: int | None = None,
) -> RespuestaTexto:
    """Mismo comportamiento que `generar_texto` (ver sus parámetros), pero
    devuelve también `MetricasOllama` -- usada por `comun.uso_llm` para
    registrar el uso sin tener que repetir la llamada HTTP."""
    base_url = os.environ.get("LLM_BASE_URL", "http://ollama:11434")
    modelo_principal = modelo if modelo is not None else os.environ.get("LLM_MODEL_PRINCIPAL", "")
    keep_alive = os.environ.get("OLLAMA_KEEP_ALIVE", "24h")
    opciones: dict[str, object] = {
        "temperature": TEMPERATURA_POR_DEFECTO,
        "seed": SEMILLA_POR_DEFECTO,
    }
    if num_ctx is not None:
        opciones["num_ctx"] = num_ctx
    if num_predict is not None:
        opciones["num_predict"] = num_predict

    cuerpo: dict[str, object] = {
        "model": modelo_principal,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "keep_alive": keep_alive,
        "options": opciones,
    }
    if formato is not None:
        cuerpo["format"] = formato
    if pensamiento is not None:
        cuerpo["think"] = pensamiento
    respuesta = httpx.post(f"{base_url}/api/chat", json=cuerpo, timeout=timeout)
    respuesta.raise_for_status()
    cuerpo_respuesta = respuesta.json()
    metricas = MetricasOllama(
        modelo=modelo_principal,
        tokens_entrada=cuerpo_respuesta.get("prompt_eval_count"),
        tokens_salida=cuerpo_respuesta.get("eval_count"),
        duracion_total_ms=ns_a_ms(cuerpo_respuesta.get("total_duration")),
        duracion_carga_ms=ns_a_ms(cuerpo_respuesta.get("load_duration")),
        duracion_lectura_ms=ns_a_ms(cuerpo_respuesta.get("prompt_eval_duration")),
        duracion_generacion_ms=ns_a_ms(cuerpo_respuesta.get("eval_duration")),
    )
    return RespuestaTexto(texto=cuerpo_respuesta["message"]["content"], metricas=metricas)


def generar_texto(
    prompt: str,
    *,
    modelo: str | None = None,
    timeout: float = 300.0,
    formato: str | dict | None = None,
    pensamiento: str | None = None,
    num_ctx: int | None = None,
    num_predict: int | None = None,
) -> str:
    """`formato="json"` (o un esquema JSON como dict, soportado por Ollama
    para salida estructurada) reduce la chance de que el modelo agregue
    texto antes/después del objeto esperado -- quien llama sigue
    necesitando parsear con tolerancia (nunca hay garantía absoluta).
    `pensamiento` ("low"/"medium"/"high") controla el esfuerzo de
    razonamiento de modelos que lo soportan (gpt-oss) -- `None` deja el
    comportamiento por defecto del modelo. `num_ctx`/`num_predict` acotan
    el contexto y la longitud de salida (CU-02: evita respuestas más
    largas de lo necesario en hardware sin GPU)."""
    resultado = generar_texto_con_metricas(
        prompt,
        modelo=modelo,
        timeout=timeout,
        formato=formato,
        pensamiento=pensamiento,
        num_ctx=num_ctx,
        num_predict=num_predict,
    )
    ULTIMAS_METRICAS_LLM.set(resultado.metricas)
    return resultado.texto
