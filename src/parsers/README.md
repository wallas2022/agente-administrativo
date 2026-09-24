# src/parsers

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** RF-03, RF-06, RF-07, RF-08, RF-09, RF-10

## Propósito

Extracción estructurada de contenido desde documentos administrativos: hojas/celdas de Excel (openpyxl), texto/estructura de Word (python-docx), diapositivas de PowerPoint (python-pptx) y texto/layout de PDF (Docling, PyMuPDF).

## Entradas

Archivo original del documento administrativo (según tipo).

## Salidas

Representación estructurada normalizada del documento, consumida por validadores, ortografía y RAG.

## RF que cubre

RF-03, RF-06, RF-07, RF-08, RF-09, RF-10 (ver [docs/01-requerimientos/04-matriz-trazabilidad.md](../../docs/01-requerimientos/04-matriz-trazabilidad.md)).

Sin lógica de negocio implementada (solo esqueleto/interfaces).
