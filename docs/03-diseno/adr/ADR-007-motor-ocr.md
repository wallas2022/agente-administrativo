# ADR-007 — Motor OCR (Tesseract + OpenCV, tessdata_best offline)

**Versión:** 1.0
**Fecha:** 2026-10-01
**Relacionado con:** RF-11, HU-05, CU-06, PP-05, PP-06, R-05, docs/01-requerimientos/01-requerimiento-formal.md (tabla de stack tecnológico, fila "OCR")

## Estado

Aceptado.

## Contexto

La tabla de stack tecnológico del requerimiento formal ya nombra **Tesseract + OpenCV** como motor OCR principal y **PaddleOCR** como alternativa (fila "OCR" de esa tabla) — esta decisión en sí no es nueva, viene documentada desde antes de este bloque. `src/ocr/README.md` ya existe como esqueleto vacío que anticipa exactamente esto ("Extracción de texto desde imágenes (OCR) usando Tesseract + OpenCV").

Lo que **sí** es nuevo (no estaba en ningún Dockerfile/requirements.txt todavía) son las dependencias concretas para implementarlo: nada de Tesseract, OpenCV, pytesseract ni tessdata está instalado hoy en ninguna imagen.

**Nota sobre la cita "R-11" de la tarea:** el contexto de la tarea dice "R-11 (stage sin AVX: Tesseract sí, PaddleOCR no)", pero en `01-requerimiento-formal.md` **R-11 es otro riesgo** ("Autoaprobación permitida por defecto reduce el control de cuatro-ojos", §15) -- no tiene nada que ver con OCR ni con AVX. No encontré ninguna mención de "AVX" en `docs/`. Asumo que el dato de hardware (stage sin instrucciones AVX, que `paddlepaddle` normalmente requiere y Tesseract no) es información nueva que tienes y todavía no está en ningún documento -- la uso igual como justificación técnica porque refuerza la elección que ya estaba documentada (Tesseract como principal), pero **marco esto como [POR CONFIRMAR]** y sugiero registrarlo como una fila nueva de riesgo (o una nota en ADR-001/ADR-004) en vez de seguir citándolo como "R-11".

## Decisión

1. **Motor:** Tesseract 5.x (binario del sistema, paquete `tesseract-ocr` de Debian, misma base `python:3.12-slim` que ya usan `api`/`orquestador`) + `pytesseract` (binding Python, solo invoca el binario por CLI -- sin dependencias pesadas propias).
2. **Preprocesado de imagen:** `opencv-python-headless` (sin dependencias de GUI/X11, correcto para un contenedor sin pantalla) + `numpy`. Cubre orientación (OSD de Tesseract + corrección con OpenCV), enderezado (deskew), reducción de ruido y binarización adaptativa (Bloque 1 de la tarea).
3. **Rasterizado de PDF escaneado a imagen (300 DPI):** se reutiliza **PyMuPDF**, que ya es dependencia de `src/parsers/pdf.py` (`page.get_pixmap(dpi=300)`) -- **no se agrega una librería nueva de PDF** (se descartó `pdf2image`/Poppler por esto).
4. **Idiomas offline (RNF-01, sin salida a internet en runtime):** se descargan `spa.traineddata` y `eng.traineddata` de **tessdata_best** (repositorio oficial `tesseract-ocr/tessdata_best`, mayor exactitud que el paquete `tesseract-ocr-spa` de apt, que trae la variante "fast") y se copian dentro de la imagen Docker en tiempo de **build** (con internet, igual que ya pasa con `pip install`), fijando el commit/tag exacto para que el build sea reproducible. En runtime, `TESSDATA_PREFIX` apunta a esa carpeta local -- cero llamadas de red.
5. **Dónde vive en la infraestructura:** el motor OCR corre en `orquestador`/`worker` (mismo patrón que el resto de pipelines pesados de CU-01/CU-02/CU-05), no en `api` -- el Dockerfile de `api` no necesita Tesseract.
6. **Módulo:** `src/ocr/` (ya existe el README esqueleto) implementa la lógica real; expone una interfaz de salida (bloques/líneas/palabras con bbox, confianza, página, orden de lectura) que `orquestador.pipeline_ocr` (nuevo, Bloque 1) consume, siguiendo el mismo patrón de separación parser/pipeline que ya usan `parsers.excel` + `orquestador.pipeline_contable`.

## Alternativas consideradas

| Alternativa | Por qué se descarta |
| --- | --- |
| PaddleOCR | Ya es la alternativa documentada, no la principal; `paddlepaddle` requiere instrucciones AVX que el servidor de stage no tendría [POR CONFIRMAR -- ver nota arriba]. |
| EasyOCR | Basado en PyTorch: imagen Docker mucho más pesada y una dependencia de ML framework completa solo para OCR, sin evidencia de mejor exactitud para este caso (documentos institucionales, no escritura a mano). |
| Servicio OCR en la nube (Google Vision, AWS Textract, Azure Document Intelligence) | Contradice RNF-01 (sin salida a internet) -- mismo criterio que descartó un LLM en la nube en ADR-001. |
| `tesseract-ocr-spa`/`tesseract-ocr-eng` de apt (variante "fast") en vez de tessdata_best | Menor exactitud; PP-05 exige CER ≤5 % en documentos legibles, y tessdata_best es la variante que Tesseract recomienda para ese objetivo a costa de ser más lenta (aceptable: el presupuesto de PP-05 es ≤30 s/página en CPU, no tiempo real). |

## Consecuencias

- Las imágenes `orquestador`/`worker` crecen (binario de Tesseract + ~2 archivos `.traineddata` de tessdata_best, que pesan más que la variante "fast" -- unas decenas de MB cada uno -- + `opencv-python-headless`). No se mide todavía el tamaño final; se reporta en el Bloque 1.
- El Dockerfile de `orquestador` necesita una etapa `apt-get install tesseract-ocr` más la descarga de los `.traineddata` -- primera vez que una imagen de este proyecto instala un paquete del sistema operativo además de dependencias Python.
- La velocidad real en CPU (sin GPU, mismo hardware sin AVX de stage) es la incógnita principal -- PP-05 fija ≤30 s/página, a medir en el Bloque 5 contra el dataset nuevo de `tests/dataset/cu-06/`.
- Igual que RNF-03 en CU-01 y CU-02: el LLM de post-corrección (Bloque 2) nunca toca cifras/montos/fechas/códigos -- mismo principio de guardia ya aplicado en `validadores/redaccion/guardia.py`, adaptado para confusiones de caracteres OCR en vez de reescritura de redacción.
- Pendiente de confirmar [POR CONFIRMAR]: el detalle "stage sin AVX" como justificación formal -- si se confirma, debería registrarse como nota en ADR-001/ADR-004 o como una fila de riesgo nueva, no seguir citándose como "R-11".
