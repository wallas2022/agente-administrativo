# Guion de demo (sandbox local)

**Versión:** 0.1.0
**Fecha:** 2026-10-09
**Relacionado con:** docs/04-pruebas/estado-proyecto.md, docs/04-pruebas/resultados/

Pasos para demostrar el agente en el ambiente local (Docker Desktop), con datos sintéticos (sin datos reales de la organización). Requiere el stack levantado:
```bash
docker compose --env-file .env.local -f infra/compose.yml -f infra/compose.local.yml up -d
```

Este documento se arma por secciones a medida que cada caso de uso llega a un estado demostrable. Hoy solo tiene la sección de CU-06 (OCR); el resto queda pendiente.

## CU-06 — Imagen a texto (OCR)

**Precondición**: tener a mano una imagen (png/jpg/tiff/bmp) o PDF escaneado. Para la demo se puede generar uno sintético con `tests/dataset/generar_cu06.py` (texto propio, sin datos reales) -- genera `tests/dataset/cu-06/legible_render_limpio.png`, entre otros.

1. **Nuevo análisis** → tipo de revisión "Imagen a texto" → seleccionar el archivo (o varios: se crea un análisis por archivo) → "Iniciar análisis".
2. **Agente trabajando**: mientras el worker procesa, la bitácora en vivo muestra "Análisis iniciado" y, al terminar el motor, "OCR completado — N página(s), confianza media X%, N ilegible(s)" (el resumen real del motor, no un contador de progreso por página -- ver docs/04-pruebas/resultados/local-cu06-bloque3.md, decisión de alcance #1).
3. **Resultado**: vista lado a lado -- la imagen original a la izquierda, el texto reconocido a la derecha. Si el motor marcó alguna palabra con confianza baja/media, aparece resaltada en rojo/amarillo.
   - Si el documento es demasiado ilegible para reconocer nada con confianza, se muestra un aviso en vez de un texto inventado (RN-06, PP-06) -- probar con una foto muy desenfocada o de muy bajo contraste para ver este caso.
4. **Editar texto**: botón "Editar texto" → corregir manualmente → "Guardar". El cambio queda persistido (y auditado en bitácora como "ocr_edicion_manual").
5. **Copiar** / **Descargar .txt** / **Descargar .docx** (esta última con las palabras dudosas resaltadas en el propio Word).
6. **Continuar con "Revisar ortografía" o "Mejorar redacción"**: toma el texto ya reconocido (con las ediciones manuales si las hubo) y abre un análisis nuevo de CU-05 o CU-02 sobre ese mismo texto -- sin tener que volver a cargar nada.

**Qué NO mostrar como garantizado**: el dataset de prueba es sintético (texto renderizado por computadora); sobre una fotografía real de un documento físico el CER puede ser mayor que en esta demo (ver [docs/04-pruebas/casos-prueba/PP-05.md](casos-prueba/PP-05.md), limitación documentada).

## Pendiente

- Secciones de CU-01 (Excel contable), CU-02 (redacción), CU-05 (ortografía) y CU-08 (base de conocimiento) -- ya tienen funcionalidad documentada en `docs/04-pruebas/resultados/`, pero no un guion de demo paso a paso todavía.
