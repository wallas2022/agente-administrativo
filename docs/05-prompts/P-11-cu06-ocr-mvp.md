# P-11 · CU-06 · OCR imagen/PDF escaneado a texto (fase 1, MVP)

Versión 1.0 · 2026-10-08 · Base: P-08 (especificación base), P-09 (fija umbrales), docs/02-analisis/04-analisis-cu06-ocr.md

## Prompt

```xml
<tarea>Implementa la fase 1 (MVP) de CU-06 OCR: imagen o PDF escaneado → texto, según docs/05-prompts/P-11-cu06-ocr-mvp.md (P-08 es la especificación base; P-09 fija umbrales). El diagnóstico ya está hecho: no hay código de OCR; no lo repitas. Responde en español. Detente al final de cada bloque y espera mi visto bueno.</tarea>

<contexto>
RF-11, HU-05, PP-05 (CER ≤5 % en legibles), PP-06 (100 % ilegibles informados, 0 texto inventado), R-05, R-11, ADR-007.
Reutiliza: cola Celery y despacho por tipo_revision en src/orquestador/orquestador/tareas.py, _marcar_fallido y bitácora, almacenamiento S3 (comun/almacenamiento.py), retención de 90 días, migraciones Alembic, patrón "publicar primero" de CU-05.
Sin red en ejecución: tesseract-ocr 5 y tessdata_best spa+eng se instalan en el build de la imagen del orquestador/worker; nada se descarga al correr. Stage sin AVX.
Sin LLM en esta fase. Ninguna cifra, monto, fecha ni código se modifica jamás.
</contexto>

<documentacion>
Antes del bloque 1, crea docs/02-analisis/04-analisis-cu06-ocr.md (máx. 1 página): antecedentes, objetivo general y específicos, In-Scope/Out-of-Scope, stack, RF/RNF afectados, riesgos, flujo Mermaid. Usa solo Mermaid para diagramas.
</documentacion>

<bloque id="1" nombre="Motor">
1. src/ocr/: entrada png, jpg, tiff, bmp y PDF. En PDF, páginas con texto nativo (PyMuPDF) se usan tal cual; páginas sin texto se rasterizan a 300 DPI.
2. Preprocesado OpenCV: OSD y rotación, enderezado (deskew), reducción de ruido, binarización adaptativa, escalado a ≥300 DPI.
3. Tesseract (spa+eng, OEM LSTM): resultado por página con palabras (texto, bbox, confianza), líneas en orden de lectura y confianza media.
4. Nuevo tipo_revision "ocr" (migración Alembic + semilla) y su rama en tareas.py.
5. Dockerfile del orquestador/worker: tesseract + tessdata_best spa/eng; prueba que falle si falta spa.traineddata o si el build necesita red en ejecución.
6. Donde CU-05/CU-02 hoy fallan con "PDF sin texto / requiere OCR", ofrece en el mensaje la opción de procesarlo con CU-06 (no lo encadenes en automático todavía).
</bloque>

<bloque id="2" nombre="Calidad sin inventar">
1. Umbrales en .env y .env.*.example: OCR_CONF_DUDOSA=60 (rojo), OCR_CONF_REVISAR=80 (amarillo), OCR_PAGINA_ILEGIBLE=50.
2. Página con confianza media <OCR_PAGINA_ILEGIBLE o casi sin texto → estado "ilegible", mensaje claro y cero texto para esa página. Documento con todas las páginas ilegibles → análisis completado con aviso, no fallido.
3. Post-corrección solo como sugerencias: LanguageTool + glosario (RN-06). Nunca autocorrige. Tokens con dígitos, montos, fechas y códigos quedan excluidos de cualquier sugerencia.
4. Cada palabra dudosa es un hallazgo (página, línea, texto, confianza, nivel) para reutilizar la vista de hallazgos.
</bloque>

<bloque id="3" nombre="Interfaz básica">
1. Habilita "Imagen a texto" en Nuevo análisis: carga de uno o varios archivos (mismos límites de tamaño), progreso "Página N de M".
2. Resultado: vista lado a lado imagen | texto, palabras dudosas resaltadas (rojo/amarillo), edición manual del texto, botón Copiar.
3. Descargar .txt y .docx (dudosas resaltadas en el .docx).
4. Botones "Revisar ortografía" (CU-05) y "Mejorar redacción" (CU-02) que crean un análisis nuevo con el texto obtenido.
5. Bitácora: archivo, páginas, confianza media, páginas ilegibles, ediciones y descargas.
</bloque>

<bloque id="4" nombre="Dataset, pruebas y cierre">
1. tests/dataset/cu-06/ generado por script con textos propios (sin datos reales), incluyendo montos "Q 1,250.00", fechas y siglas del glosario: (a) 3 legibles: render limpio, foto con perspectiva leve, rotada 90°; (b) 1 PDF escaneado de 2 páginas; (c) 2 de baja calidad: desenfoque fuerte y bajo contraste. Hoja de respuestas con el texto esperado.
2. Tests (TDD): CER con Levenshtein propio (PP-05 ≤5 % en a y b), PP-06 (c informada como ilegible, 0 texto inventado), 0 cifras alteradas, rotación detectada, segundos por página.
3. Mide dentro del contenedor del worker con límites de stage (8 CPU) y registra en docs/04-pruebas/resultados/local-CU06.md.
4. Actualiza plan-pruebas, matriz de trazabilidad, estado-proyecto y docs/04-pruebas/guion-demo-sandbox.md (sección OCR).
</bloque>

<reglas>TDD: primero pruebas, luego código. Un commit por bloque (Conventional Commits) y push. Sin secretos ni datos reales. No agregues librerías fuera de ADR-007 (Tesseract, OpenCV, PyMuPDF) sin proponer un ADR. No mostrar archivos completos en el chat.</reglas>

<salida_en_chat>Por bloque: tabla ruta · cambio · prueba (ok/falla) · métrica · "¿Continúo con <siguiente>?".</salida_en_chat>
```
