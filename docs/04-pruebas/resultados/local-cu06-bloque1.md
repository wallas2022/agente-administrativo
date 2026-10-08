# Resultados — CU-06 "OCR imagen/PDF escaneado a texto", Bloque 1 (Motor)

**Versión:** 0.1.0
**Fecha:** 2026-10-08
**Relacionado con:** docs/02-analisis/04-analisis-cu06-ocr.md, docs/05-prompts/P-08/P-09/P-11-cu06-ocr-mvp.md, RF-11, HU-05, PP-05, PP-06, ADR-007

## Alcance

Motor de OCR de punta a punta (imagen o PDF → texto), sin interfaz todavía (Bloque 3) y sin clasificación de confianza por umbral ni hallazgos de "palabra dudosa" (RN-06, Bloque 2). Incluye el paquete `src/ocr/`, la nueva rama `tipo_revision == "ocr"` en el orquestador, y el Dockerfile con Tesseract + `tessdata_best` spa/eng.

## Backend

| Ruta | Cambio | Prueba | Métrica |
| --- | --- | --- | --- |
| `src/ocr/preprocesamiento.py` (nuevo) | Enderezado (deskew vía PCA sobre píxeles de primer plano — no `cv2.minAreaRect`, cuyo rango de ángulo cambia entre versiones de OpenCV), reducción de ruido (`fastNlMeansDenoising`), binarización adaptativa, escalado a ≥300 DPI. Puro OpenCV, sin Tesseract | `tests/unit/test_ocr_preprocesamiento.py` (9 casos) | 9 passed en 0.69 s |
| `src/ocr/orientacion.py` (nuevo) | Corrección de orientación gruesa (OSD 0/90/180/270°); `FuncionOsd` inyectable (mismo patrón que `FuncionLLM`/`FuncionRevisarLT`) — la implementación real (`detectar_rotacion_tesseract`) envuelve `pytesseract.image_to_osd` | `tests/unit/test_ocr_orientacion.py` (4 casos, con fakes) | 4 passed en 0.39 s |
| `src/ocr/modelos.py` (nuevo) | `Palabra`/`Línea`/`ResultadoPagina` (bbox, confianza, texto, `texto_nativo`) | cubierto por los módulos que lo usan | cobertura 100 % |
| `src/ocr/motor.py` (nuevo) | Orienta → preprocesa → pasa por Tesseract (spa+eng, `--oem 1`); agrupa palabras en líneas en orden de lectura (el orden de las filas de `image_to_data`, sin reordenar); `FuncionOcr` inyectable | `tests/unit/test_ocr_motor.py` (5 casos, con fakes) | 5 passed en 0.49 s |
| `src/ocr/documentos.py` (nuevo) | Punto de entrada por archivo: imagen suelta (png/jpg/jpeg/tiff/tif/bmp) o PDF; en PDF, página con texto nativo se usa tal cual (PyMuPDF, nunca pasa por Tesseract), página sin texto se rasteriza a 300 DPI | `tests/unit/test_ocr_documentos.py` (6 casos: imagen, tipo no soportado, PDF nativo, PDF escaneado) | 6 passed en 3.44 s |
| `src/ocr/requirements.txt` (nuevo) | `opencv-python-headless==5.0.0.93`, `pytesseract==0.3.13`, `numpy==2.5.3`, reutiliza `parsers/requirements.txt` (PyMuPDF) | — | sin librerías fuera de ADR-007 |
| `src/orquestador/orquestador/pipeline_ocr.py` (nuevo) | Corre el motor y publica el texto reconocido como nueva `VersionDocumento` (`es_corregida=True`), mismo patrón que la versión marcada de CU-01 | `tests/unit/test_pipeline_ocr.py` (2 casos) | 2 passed en 9.91 s; cobertura 100 % |
| `src/orquestador/orquestador/tareas.py` | Nueva rama `tipo_revision.nombre == "ocr"` en `ejecutar_analisis`; inyección real (`ocr_imagen_tesseract`, `detectar_rotacion_tesseract`) en `analizar_documento` | `tests/unit/test_orquestador_tareas.py` (+1 caso, extremo a extremo con `moto`) | 3 passed en 6.95 s |
| `src/orquestador/Dockerfile` | `apt-get install tesseract-ocr`; descarga `tessdata_best` spa/eng (build-time, no runtime); `test -f` falla el build si falta `spa.traineddata`/`osd.traineddata`; agrega `COPY ocr/requirements.txt` + `COPY ocr ./ocr` | build Docker real (ver abajo) | build OK, ~268 s (capa de pip, con caché de red) |
| `src/parsers/pdf.py` | `PdfSinTextoError`: el mensaje ahora ofrece CU-06 ("Imagen a texto") como opción en vez de "iteración 2" (ya no aplica — CU-06 existe); no se encadena automático | `tests/unit/test_parser_pdf.py`, `test_curaduria_extraccion.py` (sin cambios, siguen en verde: solo exigían `match="OCR"`) | 12 passed |

```
tests/unit (suite completa): 351 passed in 78.47 s
ruff check src tests: sin hallazgos
mypy src: sin hallazgos (9 archivos nuevos/tocados; 2 ajustes de tipo: PCACompute con `mean` explícito, `# type: ignore[call-overload]` puntual en pixmap.height/width — stub de PyMuPDF los declara como método, en tiempo de ejecución son enteros)
```

### Verificación de imagen Docker (build real + Tesseract real, sin fakes)

```
docker build -f orquestador/Dockerfile --build-context kb=../kb .  -> build OK (~268 s)
docker run ... tesseract --list-langs                              -> eng, osd, spa
docker run ... (OCR real sobre imagen sintética "Factura Q 1,250.00")
  -> TEXTO: 'Factura Q 1,250.00'
  -> CONFIANZA: 94.0
```

Esta es la única prueba de este bloque que usa el Tesseract **real** (todas las unitarias usan `funcion_ocr`/`funcion_osd` inyectados, nunca el binario) — confirma que la imagen construida reconoce texto en español/inglés y preserva montos exactos (RNF-03).

## Decisión: sin migración para `tipo_revision == "ocr"`

P-11 pedía "migración Alembic + semilla" para el nuevo `tipo_revision`. Se verificó que **ningún** tipo existente (`contable`, `ortografia`, `redaccion`) tiene migración ni semilla — los tres se crean perezosamente en `api/main.py` (`sesion.query(TipoRevision).filter_by(nombre=...).one_or_none()`, si no existe se crea). Para no romper esa consistencia (y no agregar una migración que ningún otro tipo necesitó), `"ocr"` sigue el mismo patrón: se crea solo la primera vez que alguien sube un documento con `tipo_revision="ocr"`. [POR CONFIRMAR con el usuario si esto es aceptable o si se prefiere una migración explícita de todas formas.]

## Hallazgos de este bloque

1. **`cv2.minAreaRect` no es portable entre versiones de OpenCV** (el rango/signo de su ángulo cambió en versiones recientes) — se evitó por completo usando PCA sobre los píxeles de primer plano para el ángulo de inclinación, que no depende de esa convención.
2. **El orden de lectura de Tesseract no necesita reordenarse**: `pytesseract.image_to_data` ya emite las filas en orden de lectura; agrupar por `(block_num, par_num, line_num)` respetando el orden de inserción del diccionario (Python 3.7+) basta.
3. **`python:3.12-slim` es Debian trixie**: Tesseract 5.5.0, tessdata en `/usr/share/tesseract-ocr/5/tessdata/`, con `osd.traineddata` y `eng.traineddata` (rápido) ya incluidos — solo hubo que agregar `spa.traineddata` y reemplazar `eng.traineddata` por la versión `tessdata_best`.

## Pendiente (antes del Bloque 2)

- Clasificación de confianza por umbral (`OCR_CONF_DUDOSA`, `OCR_CONF_REVISAR`, `OCR_PAGINA_ILEGIBLE`) y persistencia de "palabra dudosa" como `Hallazgo`.
- Post-corrección por sugerencias (LanguageTool + glosario), excluyendo tokens con dígitos/montos/fechas/códigos.
- Interfaz (Bloque 3) y dataset/mediciones de CER (Bloque 4) — las medidas de hoy son de humo (una imagen sintética), no las métricas PP-05/PP-06 formales, que requieren el dataset de `tests/dataset/cu-06/` del Bloque 4.
