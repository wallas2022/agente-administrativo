# src/rag

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** RF-05, RF-12, RF-16

## Propósito

Recuperación de conocimiento controlado (RAG): indexación de fuentes normativas, glosario y reglas en Qdrant usando embeddings bge-m3, y recuperación de fragmentos relevantes para el análisis y la generación de hallazgos.

## Entradas

Fuentes de conocimiento (`kb/fuentes`, `kb/reglas`, `kb/glosario`). Consultas del orquestador durante el análisis.

## Salidas

Fragmentos relevantes con referencia a la fuente y fecha de vigencia.

## RF que cubre

RF-05, RF-12, RF-16 (ver [docs/01-requerimientos/04-matriz-trazabilidad.md](../../docs/01-requerimientos/04-matriz-trazabilidad.md)).

Sin lógica de negocio implementada (solo esqueleto/interfaces).
