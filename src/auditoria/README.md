# src/auditoria

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** RF-18, RF-19

## Propósito

Registro inmutable de bitácora: quién cargó, quién revisó, qué decisión se tomó y cuándo, para trazabilidad y cumplimiento.

## Entradas

Eventos de negocio emitidos por `src/api`, `src/orquestador` y `src/auth`.

## Salidas

Registros de bitácora persistidos (entidad `bitacora`, ver `docs/03-diseno/er/modelo-datos.md`), consultables por el rol Auditor.

## RF que cubre

RF-18, RF-19 (ver [docs/01-requerimientos/04-matriz-trazabilidad.md](../../docs/01-requerimientos/04-matriz-trazabilidad.md)).

Sin lógica de negocio implementada (solo esqueleto/interfaces).
