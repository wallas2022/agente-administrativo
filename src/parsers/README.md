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

## Estado

- `excel.py`: parser del libro contable de CU-01 (esquema fijo Cuenta|Descripcion|...|Moneda|Asiento).
- `docx.py`, `pptx.py`, `xlsx.py`, `pdf.py`, `texto_plano.py`: extractores de texto de CU-05 (RF-10, Bloque O1) — devuelven `SegmentoTexto` (texto + ubicación exacta re-localizable: párrafo, celda, diapositiva, página) para que `src/ortografia` revise el contenido sin perder dónde corregirlo (RF-14). `pdf.py` levanta `PdfSinTextoError` si el PDF no tiene capa de texto (requiere OCR, CU-06, iteración 2).
- Resto de tipos de revisión: sin lógica de negocio implementada todavía.
