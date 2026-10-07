# P-08 · CU-06 · OCR imagen/PDF escaneado a texto

**Reconstruido el 2026-10-07** a partir del prompt original recibido en sesión (nunca se había guardado como archivo) -- es la base que cita P-09 ("Base: P-08"). Se guarda tal cual se recibió, sin editar contenido.

Trazabilidad: RF-11, HU-05, PP-05, PP-06, R-05, R-11, ADR-007.

## Prompt

```xml
<tarea>Implementa CU-06 OCR (imagen/PDF escaneado → texto) según docs/05-prompts/P-08-cu06-ocr-imagen-a-texto.md. Responde en español. Detente al final de cada bloque.</tarea>

<contexto>RF-11, HU-05, PP-05 (CER ≤5 % en legibles), PP-06 (100 % informa ilegible), R-05, R-11 (stage sin AVX: Tesseract sí, PaddleOCR no). Reutiliza cola, bitácora, retención, UI y conversor de salida de CU-02/CU-05. Sin internet: traineddata spa+eng (tessdata_best) dentro de la imagen Docker. Proponer ADR antes de agregar librerías o modelos nuevos.</contexto>

<bloque id="1" nombre="Motor OCR">src/ocr/: Tesseract 5. Entrada png/jpg/tiff/bmp y PDF; páginas PDF sin texto → rasterizar a 300 DPI → OCR (reemplaza el aviso "requiere OCR"). Preprocesado OpenCV: orientación (OSD), enderezado, ruido, binarización adaptativa, ≥300 DPI. Salida: bloques/líneas/palabras con bbox, confianza, página y orden de lectura.</bloque>

<bloque id="2" nombre="Calidad y no inventar">Confianza de palabra &lt;60 = dudosa (resaltada). Página con media &lt;50 o poco texto = ilegible: informar, no generar texto. Post-corrección: LanguageTool + glosario; LLM (temperature=0, seed, una llamada por lote) solo confusiones OCR dentro de palabras; nunca cambia números, montos, fechas ni códigos; cifra dudosa → "verificar en el original".</bloque>

<bloque id="3" nombre="Tablas">Rejilla OpenCV → celdas → OCR por celda (whitelist numérica en montos) → .xlsx con dudosas en amarillo. Si tiene Debe/Haber, ofrecer "Validar como Excel contable" (CU-01).</bloque>

<bloque id="4" nombre="Interfaz y salidas">"Imagen a texto" en Nuevo análisis; vista imagen | texto con dudosos resaltados y edición manual; Copiar; Descargar .txt | .docx | .xlsx; botones "Revisar ortografía" (CU-05) y "Mejorar redacción" (CU-02). Bitácora de archivo, páginas, confianza, ediciones y descargas.</bloque>

<bloque id="5" nombre="Dataset y pruebas">tests/dataset/cu-06/ con verdad conocida y sin datos reales: 3 legibles (limpia, foto con perspectiva, rotada 90°), 1 tabla tipo libro diario (de Test01-Partidas.xlsx), 2 de baja calidad. Tests: CER ≤5 % (PP-05), ilegibles informadas con 0 texto inventado (PP-06), 0 cifras alteradas, ≤30 s por página en CPU. Actualiza plan-pruebas, estado-proyecto y demo-guion.</bloque>

<reglas>Commits por bloque, push, sin secretos ni datos reales, no mostrar archivos completos en el chat.</reglas>
<salida_en_chat>Por bloque: tabla ruta · cambio · prueba · tiempo · "¿Continúo?".</salida_en_chat>
```

## Qué pasó con este prompt la primera vez

Se ejecutó solo el análisis de la decisión de stack (Tesseract + OpenCV + tessdata_best, sin PaddleOCR por R-11/AVX), registrado en `docs/03-diseno/adr/ADR-007-motor-ocr.md` (aceptado). El trabajo se interrumpió ahí -- ningún bloque (1 a 5) llegó a implementarse antes de que la sesión cambiara a otra tarea (CU-02). Ver el diagnóstico de P-09 (Bloque 0) para el detalle verificado contra el código real.
