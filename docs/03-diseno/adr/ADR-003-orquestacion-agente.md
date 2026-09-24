# ADR-003 — Orquestación del agente (LangGraph + Celery/Redis)

**Versión:** 1.0
**Fecha:** 2026-09-24
**Relacionado con:** RF-04, RF-12, RNF-05, RNF-06, docs/01-requerimientos/01-requerimiento-formal.md §9, docs/03-diseno/c4/03-componentes-orquestador.md

## Estado

Aceptado.

## Contexto

El análisis de un documento no es una sola llamada a un LLM: implica clasificar el tipo de revisión (RF-04), enrutar a un adaptador específico según el tipo (contable, redacción, normativa, control, ortografía, OCR), consultar la base de conocimiento (RAG), invocar al LLM cuando corresponde, y ensamblar cada hallazgo con su evidencia y fuente citada (RF-12), dejando trazabilidad de qué regla, fuente, modelo y versión de prompt lo generaron (RNF-06). Además, el volumen esperado (~50 documentos/día hábil) y la meta de tiempo por documento (≤ 10 min) exigen procesar varios análisis en paralelo (RNF-05).

## Decisión

Se usa **LangGraph** (Python) para modelar el análisis como un grafo de estados con nodos explícitos (clasificador, enrutador, adaptadores por tipo de revisión, cliente RAG, generador de hallazgos), ejecutado por procesos **Celery** que consumen una cola **Redis**, con al menos 2 réplicas de `worker` en stage (RNF-05).

## Alternativas consideradas

| Alternativa | Por qué se descarta |
| --- | --- |
| n8n (orquestación low-code) | Menor control sobre lógica de negocio compleja (RN-01 a RN-09), difícil de versionar y testear como código junto con `src/`, y menos idiomático para un equipo que ya trabaja en Python/FastAPI. |
| Orquestación manual en Python puro (sin framework) | Reinventa manejo de estado, reintentos y branching que LangGraph ya resuelve; mayor esfuerzo de mantenimiento a medida que crecen los tipos de revisión (CU-01 a CU-06). |
| Airflow / Prefect | Orientados a pipelines de datos por lote (ETL), no al patrón "agente con LLM en el loop" y revisión humana intercalada (CU-07); añadirían complejidad operativa sin beneficio claro para este caso de uso. |

## Consecuencias

- El grafo de orquestación se versiona como código en `src/orquestador`, con un componente por nodo (ver docs/03-diseno/c4/03-componentes-orquestador.md).
- `worker` y `orquestador` comparten la misma imagen de contenedor (`agente-admin/orquestador`); `worker` es el proceso Celery que ejecuta el grafo definido en `orquestador`.
- Cada hallazgo persiste el modelo LLM y la versión de prompt usados (RNF-06), lo que exige que el grafo propague esos metadatos hasta el nodo generador de hallazgos.
- El número de réplicas de `worker` (2 en stage) es ajustable vía `infra/compose.stage.yml` sin cambios de código; el valor exacto para sostener ~50 documentos/día se valida en PP-13.
- Si en el futuro se requiere un motor de orquestación distinto, el cambio queda acotado a `src/orquestador`, sin afectar `api`, `src/validadores/*`, `src/ortografia` ni `src/ocr`.
