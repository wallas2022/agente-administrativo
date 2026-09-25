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

## Estructura (desde L2)

- `orquestador/tareas.py` — tarea de Celery `analizar_documento`: consume la cola y transiciona `documento`/`analisis` (docs/03-diseno/estados/estados-analisis.md), registra bitácora.
- `orquestador/__init__.py` — reexporta la app de Celery compartida (`comun/cola.py`), usada también por `worker` (mismo proceso Celery) y por `src/api` como productora.
- `orquestador/__main__.py` — proceso del servicio "orquestador" propiamente dicho: hoy es un esqueleto en espera (la orquestación real corre en `worker`); ver nota de arquitectura en el propio archivo sobre la redundancia detectada en L2.

Sin validadores de negocio todavía (contable, control, ortografía, OCR, RAG — Sprint 1). Ver docs/04-pruebas/resultados/local-L2.md.
