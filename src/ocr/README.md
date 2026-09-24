# src/ocr

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** RF-11

## Propósito

Extracción de texto desde imágenes (OCR) usando Tesseract + OpenCV, incluyendo preprocesamiento de imagen (deskew, binarización, limpieza de ruido).

## Entradas

Imagen o página escaneada (PNG, JPG, PDF escaneado).

## Salidas

Texto extraído con nivel de confianza por bloque, listo para `src/ortografia` o los validadores.

## RF que cubre

RF-11 (ver [docs/01-requerimientos/04-matriz-trazabilidad.md](../../docs/01-requerimientos/04-matriz-trazabilidad.md)).

Sin lógica de negocio implementada (solo esqueleto/interfaces).
