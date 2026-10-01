# ADR-008 — Rendimiento del LLM en CU-02 (fase 2): no se llegó a ≤60 s de forma confiable, no se cambia el modelo por defecto

**Versión:** 1.0
**Fecha:** 2026-10-01
**Relacionado con:** ADR-001 (motor LLM en CPU), RF-07, RF-12, docs/04-pruebas/resultados/local-cu02-rendimiento.md

## Estado

Propuesta (decisión de modelo pendiente del responsable del proyecto -- esta sesión no cambia `LLM_MODEL_PRINCIPAL`).

## Contexto

La tarea pedía bajar el tiempo de la primera tarjeta de CU-02 (fase 2) de 208s a ≤60s en CPU, sin quitar las 2 opciones de estilo, y explícitamente: *"Si con todo no se llega a ≤60s, no cambies de modelo: propón un ADR con 1–2 modelos sin razonamiento y su medición."* Este documento es esa propuesta.

Se aplicaron todas las optimizaciones pedidas (Bloques 2-6, ver resultados): llamadas de una sola opción en texto plano (no 2 opciones en un JSON), `think="low"`, `num_ctx=2048`, `num_predict=400`, motivos calculados en Python (no por el LLM), y se salta el LLM por completo en párrafos cortos y limpios. Estas reducen de verdad el trabajo que el modelo tiene que hacer: de ~622 tokens de salida (76% de ellos "thinking") a ~44-332 tokens según el caso.

**El problema no resuelto es otro**: medido contra `gpt-oss:20b` real en este hardware (CPU, sin GPU, ver ADR-001), el tiempo de respuesta **varía de forma muy amplia e impredecible** para solicitudes de complejidad similar -- se midieron tiempos de 7.9s, 10.4s, 25.5s, 71.4s, 94.3s, 111.1s, 135.6s y 208.8s para la misma clase de párrafo con los mismos parámetros. La variable que más se correlaciona con los tiempos altos es `load_duration` (Ollama recargando el modelo de 13.8 GB a RAM): a veces es ~0.15s (modelo ya en memoria), otras veces 10-53s -- no se identificó con certeza la causa exacta (posibles candidatos: presión de memoria de otros procesos en esta misma máquina de desarrollo, incluidos los propios builds de Docker de esta sesión; o el comportamiento de `keep_alive` de Ollama al alternar llamadas desde el proceso del host y desde el contenedor de la API vía `host.docker.internal`). Esto ya estaba documentado como riesgo en ADR-001 ("el rendimiento medido en local no es representativo... RNF-04 se valida solo en stage").

## Medición: gpt-oss:20b vs. llama3.2:3b (mismo prompt, una sola opción)

Párrafo de prueba: *"el dia de hoy se aprobo el pago a proveedores por Q 1,250.00, el cual fue revisado por la DAF."* Mismos parámetros (`think` no aplica a llama3.2, no es un modelo de razonamiento): `num_ctx=2048`, `num_predict=400`, `temperature=0`, `seed=42`.

| Modelo | Tiempo | `load_duration` | `eval_count` | Resultado |
| --- | --- | --- | --- | --- |
| `llama3.2:3b` | 17.7 s | 10.3 s | 41 tokens | **Alteró el monto**: cambió "Q" por "S/" (símbolo de sol peruano) y **expandió la sigla "DAF"** a "Dirección de Administración Financiera" (inventado) |
| `gpt-oss:20b` | 111.1 s | 52.7 s | 223 tokens | Correcto: conservó "Q 1,250.00" y "DAF" intactos |

**Esta única medición de `llama3.2:3b` habría sido descartada por la guardia ampliada (Bloque 5)**: la sigla "DAF" desaparece del texto reescrito, así que `siglas_original != siglas_sugerido` y la opción se rechaza automáticamente -- el sistema no habría dejado pasar el error a un usuario. Pero sigue siendo una señal de menor confiabilidad de contenido que no se puede ignorar solo por ser 6x más rápido.

No se midió `qwen2.5:14b` ni `qwen3:30b` (también instalados localmente) por tiempo -- quedan como candidatos adicionales para una medición futura si se decide seguir este camino.

## Decisión

**No se cambia `LLM_MODEL_PRINCIPAL` en este bloque.** Se documentan las opciones para que el responsable del proyecto decida:

1. **Mantener `gpt-oss:20b`** (statu quo): las optimizaciones de este bloque reducen el trabajo real del modelo de forma medible, pero el tiempo de respuesta en este hardware sigue siendo alto e impredecible: entre ~8s y ~210s según el momento. Sin GPU (ADR-001), esto puede no cambiar hasta que exista hardware de stage.
2. **Evaluar `llama3.2:3b` (u otro modelo sin razonamiento) para CU-02 fase 2**: consistentemente más rápido en la única muestra medida (17.7s vs. 111.1s), pero con un fallo de contenido real en esa misma muestra (símbolo de moneda alterado, sigla expandida/inventada). Antes de adoptarlo haría falta: (a) una medición con una muestra más grande de párrafos reales (no solo 1), (b) confirmar que la guardia ampliada (Bloque 5) atrapa estos casos de forma consistente, y (c) una prueba de recall de "no inventar" similar a PP-05/PP-06 (CU-06) pero para CU-02, hoy inexistente.
3. **Reservar `qwen2.5:14b`/`qwen3:30b` para una medición futura** si ninguna de las dos anteriores convence -- no se evaluaron en este bloque.

## Consecuencias

- El objetivo de ≤60s de la tarea **no se cumple de forma confiable** con el modelo actual en este hardware -- sí se cumple en una fracción de las corridas (las que no necesitan recargar el modelo), documentado como variable, no como garantía.
- Las optimizaciones de este bloque (prompt corto, una opción por llamada, `think="low"`, saltar párrafos limpios) **se mantienen** independientemente de qué modelo se use a futuro -- reducen el trabajo real sin importar cuál sea el motor de inferencia.
- Si se investiga más a fondo la causa de los `load_duration` altos (¿contención de memoria en esta máquina de desarrollo? ¿comportamiento de `keep_alive` entre el host y el contenedor?), podría resolverse sin cambiar de modelo -- queda como pendiente técnico, no de producto.
- Re-evaluar con hardware de stage (GPU, ADR-005) sigue siendo la vía más segura para cumplir RNF-04-like en CU-02, igual que para CU-01/CU-05.
