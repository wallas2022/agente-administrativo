# src/ortografia

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** RF-10, RF-17

## Propósito

Corrección ortográfica y de redacción sobre texto extraído de Excel, Word, PowerPoint y PDF, usando LanguageTool con locale es-GT.

## Entradas

Texto plano extraído por `src/parsers` o `src/ocr`.

## Salidas

Lista de sugerencias de corrección con posición en el documento original y tipo de error.

## RF que cubre

RF-10, RF-17 (ver [docs/01-requerimientos/04-matriz-trazabilidad.md](../../docs/01-requerimientos/04-matriz-trazabilidad.md)).

Sin lógica de negocio implementada (solo esqueleto/interfaces).
