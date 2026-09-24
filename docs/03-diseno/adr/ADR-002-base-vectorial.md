# ADR-002 — Base vectorial para la búsqueda de conocimiento (Qdrant)

**Versión:** 1.0
**Fecha:** 2026-09-24
**Relacionado con:** RF-05, RF-12, RF-16, OE-05, docs/01-requerimientos/01-requerimiento-formal.md §9

## Estado

Aceptado.

## Contexto

El sistema necesita recuperar, para cada análisis, los fragmentos de la base de conocimiento (normativa, reglas, checklists, glosario) más relevantes para fundamentar cada hallazgo con una fuente citada (RF-12). La base de conocimiento del piloto es pequeña (20–50 documentos, SRS §5) pero debe soportar filtrado por área, vigencia y tipo de fuente (RF-16), y operar completamente on-premise (RNF-01).

## Decisión

Se usa **Qdrant** como base vectorial, con embeddings generados por **bge-m3**. Los fragmentos se indexan con metadatos (`area_id`, `fuente_id`, `estado` vigente/obsoleta, `vigente_desde`) para permitir filtrado combinado con búsqueda semántica en la misma consulta.

## Alternativas consideradas

| Alternativa | Por qué se descarta |
| --- | --- |
| pgvector (extensión de PostgreSQL) | Evita un servicio adicional, pero el filtrado combinado con metadatos y el rendimiento de búsqueda aproximada (HNSW) son menos maduros que en una base vectorial dedicada; se reconsiderará si el volumen de fragmentos permanece pequeño y se busca simplificar la infraestructura. |
| Chroma | Más simple de operar para prototipos pequeños, pero con menor madurez para filtrado avanzado por metadatos y persistencia en producción en el momento de esta decisión. |

## Consecuencias

- Se agrega `qdrant` como servicio propio en `infra/compose.yml`, con volumen persistente `qdrant_data`.
- Toda fuente de conocimiento nueva o actualizada pasa por el flujo de indexación de docs/03-diseno/flujos/ingesta-conocimiento.md antes de estar disponible para RAG.
- Al marcar una fuente como `obsoleta` (versionado), sus fragmentos deben excluirse de las búsquedas activas sin eliminarse físicamente (trazabilidad histórica) — se implementa por filtro de metadato `estado = vigente` en cada consulta (ver PP-08: 0 citas a versiones obsoletas).
- Dado el volumen pequeño del piloto (20–50 documentos), el dimensionamiento de recursos de Qdrant es modesto (ver límites en `infra/compose.local.yml` / `infra/compose.stage.yml`); deberá revisarse si la base de conocimiento crece significativamente.
