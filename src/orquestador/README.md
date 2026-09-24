# src/orquestador

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** RF-04, RF-05, RF-12

## Propósito

Orquesta el flujo de análisis de un documento como grafo de estados (LangGraph): clasifica el tipo de documento, invoca al validador correspondiente, consulta la base de conocimiento (RAG) y enruta hallazgos hacia revisión humana.

## Entradas

Eventos de nuevo documento cargado (desde `src/api` vía Redis). Metadatos del documento (tipo, área, usuario que carga).

## Salidas

Estado de análisis actualizado en PostgreSQL. Hallazgos estructurados enviados a revisión. Registros de auditoría (vía `src/auditoria`).

## RF que cubre

RF-04, RF-05, RF-12 (ver [docs/01-requerimientos/04-matriz-trazabilidad.md](../../docs/01-requerimientos/04-matriz-trazabilidad.md)).

Sin lógica de negocio implementada (solo esqueleto/interfaces).
