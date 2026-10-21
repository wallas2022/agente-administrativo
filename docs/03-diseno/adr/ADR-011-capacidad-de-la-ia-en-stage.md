# ADR-011 — Capacidad de la IA en stage: velocidad medida y opciones

**Versión:** 0.1 (propuesta)
**Fecha:** 2026-10-21
**Relacionado con:** RNF-04, RNF-05, R-02, R-11, ADR-001, ADR-005, ADR-008, docs/04-pruebas/resultados/stage-P15.md

## Estado

**Propuesta, pendiente de decisión del responsable del proyecto.** Este documento no cambia ningún modelo ni equipo; las correcciones de parámetros ya aplicadas se listan al final.

## Contexto

La prueba de carga con usuarios simultáneos del 15 al 21/10/2026 en stage (VM lab-ia-01: 20 vCPU, 121 GB de RAM, CPU virtual x86-64-v2 sobre un servidor físico sin AVX) mostró:

| Medida | Resultado |
| --- | --- |
| Ortografía (LanguageTool, sin IA en la ruta crítica) con 3, 5 y 10 usuarios simultáneos | 100 % completados; total p90 de 9.5, 7.2 y 10.8 s |
| Excel contable (con explicación por IA), 1, 3 y 5 usuarios | 0 de 9 completados: la llamada a la IA superó el límite de 300 s |
| Generación de gpt-oss:20b | **1.3 a 2.3 tokens por segundo** (12 hilos: 2.32; 20 hilos: 1.33) |
| **Lectura del prompt** de gpt-oss:20b | **~3 tokens por segundo** (73 tokens en 22–25 s) |

La lectura del prompt es el cuello de botella: en una CPU con AVX2 es una o dos órdenes de magnitud más rápida que la generación [POR CONFIRMAR: medir en un equipo con AVX2]; aquí es igual de lenta. Un prompt de 1,500 tokens tarda unos 8 minutos solo en leerse.

## Opciones

| # | Opción | A favor | En contra / riesgo |
| --- | --- | --- | --- |
| A | **Mantener gpt-oss:20b** con los ajustes de parámetros (12 hilos, prompt compacto, razonamiento bajo, tiempo máximo de 600 s, respaldo sin IA) | Sin cambio de modelo ni de equipo; el análisis nunca falla por la IA | Cada análisis con explicación tarda varios minutos; con muchos hallazgos o usuarios la mayoría cae al texto de respaldo; el chat tarda minutos |
| B | **Llevar el motor de IA a un equipo con AVX2** (opción B o C de ADR-005): Ollama en otra máquina, el resto sigue en la VM | El código ya soporta el motor desacoplado por configuración (`LLM_BASE_URL`); se espera una mejora de un orden de magnitud [POR CONFIRMAR con una medición] | Requiere un equipo; hay que asegurar que los datos no salgan de la red interna (RNF-01) |
| C | **Un modelo más pequeño y de cuantización amigable para CPU sin AVX** (por ejemplo, un modelo denso de 3–8 mil millones de parámetros en Q4) [POR CONFIRMAR cuál y su velocidad] | Es la opción más barata y rápida de probar | La calidad en español contable debe validarse (PP-01, PP-03, PP-07); cambia ADR-001 |
| D | **Reducir el uso de la IA**: explicar con plantillas (como ya se hace en RN-02 a RN-04 y RN-FORMULA) y dejar la IA para bajo demanda o para pocos hallazgos | Capacidad inmediata; no depende del hardware | Explicaciones menos ricas para RN-01 y RN-05 |

## Recomendación

Combinar **A (ya aplicada)** con una **medición de B y C** antes de comprometerse:
1. Medir los mismos tokens por segundo (generación y lectura del prompt) de gpt-oss:20b en un equipo con AVX2, aunque sea una PC.
2. Probar uno o dos modelos pequeños en stage con el mismo dataset de CU-01 y CU-05 y comparar calidad y tiempo.
3. Con esos números, decidir entre B, C o D para el piloto, y reflejarlo en la diapositiva de capacidad para los directivos.

## Correcciones de parámetros ya aplicadas (no son un cambio de modelo)

- Límite de CPU de `ollama` igual a los vCPU de la VM (antes un límite menor pausaba sus hilos el 97.8 % del tiempo).
- `LLM_NUM_THREAD=12` (12 hilos dieron 2.3 tokens/s frente a 1.3 con 20).
- Prompt de explicación compacto: 2 fragmentos de hasta 400 caracteres en vez de 3 completos.
- Razonamiento bajo y salida acotada (2,500 tokens) en CU-01; `LLM_TIMEOUT_S` configurable (600 en stage).
- Si la IA no responde a tiempo, los hallazgos de las reglas se publican con el texto de respaldo en lugar de marcar el análisis como fallido.
- `OLLAMA_NUM_PARALLEL=1` y los demás ajustes de Ollama en la plantilla de entorno.

## Consecuencias

- Hasta decidir, las cifras de capacidad con explicación por IA deben presentarse como "medidas con el hardware actual, con límite conocido", no como capacidad de producción.
- La decisión debe cerrar también el punto abierto de ADR-005 (dónde corre el motor de IA).
