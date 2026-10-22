# Capacidad en stage con usuarios simultáneos (21/10/2026)

**Ambiente:** stage `lab-ia-01` (20 vCPU, CPU virtual sin AVX). Ollama con 20 CPU, `LLM_NUM_THREAD=12`, `LLM_TIMEOUT_S=600`, `OLLAMA_NUM_PARALLEL=4`.
**Herramienta:** `tests/carga/carga_concurrente.py` (datos de prueba, un usuario analista). Relacionado: ADR-011, RNF-04, RNF-05.

## Resultados

| Escenario | Usuarios | OK / total | Total p50 (s) | Total p90 (s) | Docs/hora | Sin explicación IA |
| --- | --- | --- | --- | --- | --- | --- |
| Ortografía | 1 | 1 / 1 | 3.5 | 3.5 | 1,040 | 0 |
| Ortografía | 3 | 3 / 3 | 3.5 | 3.5 | 3,103 | 0 |
| Ortografía | 5 | 5 / 5 | 3.8 | 3.8 | 4,779 | 0 |
| Ortografía | 10 | 10 / 10 | 8.0 | 8.0 | 4,469 | 0 |
| Excel contable | 1 | 1 / 1 | 66.5 | 66.5 | 54.1 | 0 |
| Excel contable | 3 | 3 / 3 | 145.3 | 205.8 | 52.5 | 0 |
| Excel contable | 5 | 5 / 5 | 224.2 | 345.4 | 52.1 | 0 |
| Chat | 1 | 1 / 1 | 75.1 | 75.1 | 47.9 | n/a |
| Chat | 3 | 3 / 3 | 159.1 | 232.1 | 46.5 | n/a |
| Chat | 5 | 4 / 5 | 171.0 | 311.4 | 43.8 | n/a |

Los primeros hallazgos del Excel contable (reglas) salen en 3 a 13 s; el total incluye la explicación de la IA.

## Lectura

- Con la corrección de parámetros (ADR-011, opción A), el Excel contable pasó de 0 de 9 a 9 de 9 completados, sin hallazgos en texto de respaldo.
- El rendimiento de lo que usa IA se estanca en aprox. 52 Excel por hora y aprox. 45 respuestas de chat por hora: la IA atiende una petición tras otra y más usuarios solo aumentan la espera.
- Chat con 5 usuarios (prueba del chat solo, antes de corregir el tiempo máximo del chat): un error 504 (aprox. 311 s). La prueba mixta posterior ya no lo muestra.
- Ortografía no depende de la IA en la ruta crítica y escala bien hasta 10 usuarios.

## Prueba mixta (Excel, ortografía y chat a la vez)

Reparto del script: con 3 usuarios 1 de cada tipo; con 5 usuarios 2 de Excel, 2 de ortografía y 1 de chat.

| Usuarios | OK / total | Total p50 (s) | Total p90 (s) | Total máx. (s) | Docs/hora | Sin explicación IA |
| --- | --- | --- | --- | --- | --- | --- |
| 3 | 3 / 3 | 375.4 | 435.0 | 435.0 | 24.8 | 0 |
| 5 | 5 / 5 | 462.3 | 581.7 | 581.7 | 30.9 | 0 |

- Primera corrida (commit anterior a `e24df0b`): el chat dio 504 a los 371 s y 520 s porque la función del chat tenía un tiempo máximo fijo de 300 s, sin respetar `LLM_TIMEOUT_S=600`. Corregido en `e24df0b`.
- Segunda corrida (con la corrección): sin fallos, pero con 5 usuarios el máximo fue 581.7 s frente al límite de 600 s; con más carga habría errores por tiempo.
- Con la IA compartida, el rendimiento total fue de aprox. 25 a 31 documentos por hora, menor que las aprox. 52 por hora de las pruebas separadas.
- La tabla no separa los tiempos por escenario: [POR CONFIRMAR].

## Comparación de `OLLAMA_NUM_PARALLEL` (1 frente a 4), Excel contable

| Usuarios | Con 4: p50 / p90 (s) | Con 1: p50 / p90 (s) | Docs/hora con 4 | Docs/hora con 1 |
| --- | --- | --- | --- | --- |
| 1 | 66.5 / 66.5 | 66.7 / 66.7 | 54.1 | 54.0 |
| 3 | 145.3 / 205.8 | 145.6 / 209.0 | 52.5 | 51.7 |

- Sin diferencia apreciable (dentro del ruido de la medición): el límite es la CPU, que ya está ocupada con una sola generación.
- Decisión: se mantiene 4, el valor previo de stage; no se midió la mezcla chat y Excel con 1.

## Pendiente

- Decisión sobre ADR-011 (hardware con AVX2, modelo pequeño o menos uso de IA).
