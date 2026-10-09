# Resultados — CU-06 "OCR imagen/PDF escaneado a texto", Bloque 4 (Dataset, pruebas y cierre)

**Versión:** 0.1.0
**Fecha:** 2026-10-09
**Relacionado con:** docs/04-pruebas/resultados/local-cu06-bloque1.md, local-cu06-bloque2.md, local-cu06-bloque3.md, docs/04-pruebas/casos-prueba/PP-05.md, PP-06.md, docs/05-prompts/P-11-cu06-ocr-mvp.md

## Dataset

`tests/dataset/cu-06/` (generado con `tests/dataset/generar_cu06.py`, texto propio sin datos reales, sembrado con montos "Q 1,250.00"/"Q 2,500.00", fechas y siglas del glosario interno -- SFC, SAT, Banrural):

| Archivo | Tipo | Qué prueba |
| --- | --- | --- |
| `legible_render_limpio.png` | legible | caso base |
| `legible_perspectiva.png` | legible | foto en ángulo (warpPerspective leve) |
| `legible_rotada_90.png` | legible | rotación 90° -- ejercita el OSD |
| `pdf_escaneado_2paginas.pdf` | legible | PDF sin capa de texto, 2 páginas (imagen insertada) |
| `baja_calidad_desenfoque.png` | ilegible | desenfoque + ruido fuerte |
| `baja_calidad_bajo_contraste.png` | ilegible | texto casi del mismo tono que el fondo |

`respuestas.json`: texto esperado de las 4 páginas legibles (3 imágenes + las 2 páginas del PDF). Las 2 de baja calidad no tienen "texto esperado" -- PP-06 exige que se informen ilegibles, no que se les invente una transcripción. Texto sin tildes (ver nota en el propio generador): se renderiza con la fuente vectorial de OpenCV (Hershey), que no soporta acentos Unicode -- una limitación del *generador de pruebas*, no del motor real (que usa Tesseract spa+eng vía Tesseract sobre documentos reales, con soporte completo de acentos).

## Hallazgo del bloque: el deskew rompía imágenes ya derechas

Al correr el dataset contra Tesseract real por primera vez, las 3 imágenes legibles y el PDF dieron **CER entre 28 % y 53 %** (muy por encima del umbral PP-05 de 5 %) -- y una de las dos imágenes de baja calidad hacía que **todo el pipeline fallara con `TesseractError`** en vez de marcarse ilegible. Diagnóstico y causa raíz (aislando cada paso del preprocesado):

1. **`calcular_angulo_inclinacion` calculaba PCA sobre TODOS los píxeles de un bloque de varias líneas.** Para un párrafo perfectamente horizontal de 6 líneas de ancho muy distinto, eso daba un "ángulo" falso de -6.1° (en vez de 0°); `enderezar` aplicaba esa rotación espuria y destruía los glifos lo suficiente como para que Tesseract leyera "So. 00123" en vez de "Factura No. 00123". Corregido en `src/ocr/preprocesamiento.py`: ahora se agrupan las filas con contenido en "bandas" (una banda ≈ una línea) y el ángulo se calcula solo sobre la banda más densa -- una inclinación de página real afecta a todas las líneas por igual, así que una sola línea bien elegida basta y no arrastra el ruido de promediar líneas de distinto largo. Con la corrección, las 3 imágenes legibles y el PDF pasaron de CER 28-53 % a **CER 0.000**.
2. **El propio comando de OSD de Tesseract puede fallar** (`TesseractError: ... Too few characters ...`) sobre una imagen lo bastante degradada, en vez de devolver una confianza baja. Corregido en `src/ocr/orientacion.py::detectar_rotacion_tesseract`: si el OSD falla, se asume "sin rotación" (0°) y se deja que la clasificación de confianza de `ocr.calidad` (que corre siempre, nunca depende del OSD) decida si la página es ilegible -- que es exactamente lo que ya hacía antes de este bloque para el caso de "Tesseract no encuentra ninguna palabra".

Ambos cambios tienen prueba de regresión nueva en `tests/unit/test_ocr_preprocesamiento.py` (bloque de varias líneas de distinto ancho, perfectamente horizontal, ya no da un ángulo falso) y están cubiertos por la suite completa (387 unitarias, sin cambios de comportamiento para el resto de bloques).

## Medición (dataset real, Tesseract real, dentro del contenedor del worker)

Nota sobre el límite de CPU: P-11 pedía medir "con límites de stage (8 CPU)". Stage no existe todavía (ADR-005, pendiente desde el 28-oct-2026) -- se midió con el límite real configurado hoy para el worker en local (`infra/compose.local.yml`, `cpus: "1.00"`), no con 8 CPU. [POR CONFIRMAR] repetir esta medición cuando stage esté disponible.

```
docker compose ... up -d --build orquestador worker api   (con los dos fixes de arriba)
docker cp tests/dataset/cu-06 infra-worker-1:/app/tests-dataset-cu-06
docker cp tests/integration/test_cu06_pp05_pp06.py infra-worker-1:/app/
docker exec infra-worker-1 pip install --no-cache-dir pytest
docker exec -e CU06_DATASET=/app/tests-dataset-cu-06 infra-worker-1 python -m pytest test_cu06_pp05_pp06.py -v -s

legible_render_limpio.png   CER=0.000  confianza_media=94.8%  1.2 s/página
legible_perspectiva.png     CER=0.000  confianza_media=94.7%  1.1 s/página
legible_rotada_90.png       CER=0.000  confianza_media=94.8%  1.2 s/página  (OSD detectó 270°, correcto)
pdf_escaneado_2paginas.pdf  CER=0.000 / 0.000  confianza 94.0% / 95.7%  8.1 s/página (PDF rasterizado a 300 DPI, imagen más grande que las sueltas)
baja_calidad_desenfoque.png       confianza_media=0.0  texto=''  0.6 s  -> ilegible (correcto, PP-06)
baja_calidad_bajo_contraste.png   confianza_media=0.0  texto=''  0.6 s  -> ilegible (correcto, PP-06)

7 passed in 25.23 s
```

```
tests/unit (suite completa, con los fixes de este bloque): 387 passed
ruff check src tests: sin hallazgos
mypy src/ocr: sin hallazgos (9 archivos)
```

## PP-05 (CER en imágenes legibles)

**Cumple.** CER 0.000 en las 3 imágenes legibles y en las 2 páginas del PDF escaneado -- muy por debajo del umbral de 5 % (equivalente a ≥95 % de precisión, docs/04-pruebas/plan-pruebas-prototipo.md). Montos ("Q 1,250.00", "Q 2,500.00") y sigla "SAT" verificados como substrings exactos en el texto reconocido (0 cifras alteradas, RNF-03) -- no solo "dentro de la tolerancia general de CER". La rotación de 90° se detecta correctamente vía OSD real (reportó 270°, el giro correcto para enderezarla).

**Honestidad de la medición**: el dataset es sintético (texto propio renderizado con OpenCV, no fotografías/escaneos reales de documentos de Contabilidad) y pequeño (3 imágenes + 1 PDF de 2 páginas, no el dataset de producción). Un CER de 0 % sobre texto limpio renderizado por computadora es el piso, no el techo -- documentos reales (manchas, papel, impresoras de baja calidad) muy probablemente den un CER mayor que 0 % pero [POR CONFIRMAR] si seguirían bajo el umbral de 5 %. Ampliar el dataset con documentos reales/fotografiados queda pendiente (mismo riesgo R-08 ya documentado para CU-01/CU-05).

## PP-06 ("nunca inventar" en baja calidad)

**Cumple.** Las 2 imágenes de baja calidad (desenfoque fuerte, bajo contraste) se informan ilegibles (`es_pagina_ilegible` = True, confianza media 0.0, texto vacío) -- 0 texto inventado, 100 % de las ilegibles correctamente marcadas (2/2).

## Actualizaciones de documentación de este bloque

- [docs/04-pruebas/casos-prueba/PP-05.md](../casos-prueba/PP-05.md) y [PP-06.md](../casos-prueba/PP-06.md) (nuevos).
- [docs/04-pruebas/plan-pruebas-prototipo.md](../plan-pruebas-prototipo.md) §4 (registro de resultados): fila nueva para esta medición.
- [docs/01-requerimientos/04-matriz-trazabilidad.md](../../01-requerimientos/04-matriz-trazabilidad.md): verificada, sin cambios -- la fila RF-11 ya referenciaba PP-05/PP-06 (que no existían como documento hasta este bloque; ya están creados).
- [docs/04-pruebas/estado-proyecto.md](../estado-proyecto.md) (nuevo).
- [docs/04-pruebas/guion-demo-sandbox.md](../guion-demo-sandbox.md) (nuevo, sección OCR).

## Pendiente (antes del Bloque 2b)

- Dataset real/fotografiado (no solo sintético) para una medición de PP-05 con validez más allá del caso base.
- Medición en stage (8 CPU) cuando exista (ADR-005).
- Resto de bloques de CU-11 y otras iteraciones de CU-06 (tablas en imágenes, post-corrección LLM en segundo plano) quedan fuera del alcance de P-11.

---

# Bloque 2b — Soporte para capturas de pantalla

**Fecha:** 2026-10-09
**Relacionado con:** `src/ocr/capturas.py` (nuevo)

## Alcance

Una captura de pantalla (interfaz de usuario, texto antialiased y nítido) es un caso distinto de un documento escaneado/fotografiado: no tiene DPI embebido, el fondo es perfectamente plano (no la textura de papel real) y el texto suele ser mucho más chico en píxeles reales. Se detecta (`ocr.capturas.es_captura_de_pantalla`: sin DPI o DPI ≤ 96, o fondo plano) y se procesa distinto (`ocr.motor.procesar_imagen_captura`: escala x3, sin binarización adaptativa, `--psm` adaptado a si el texto está disperso, sin corrección de orientación) sin tocar el camino existente para escaneos.

**Decisión que exigió retocar el dataset del Bloque 4**: las imágenes sintéticas de `legible_*`/`baja_calidad_*` (generadas con `cv2.imwrite`, sin metadatos) tenían fondo perfectamente plano y sin DPI -- exactamente lo que ahora dispara la detección de "captura". Se les agregó un chunk PNG `pHYs` a 300 DPI y una textura de fondo leve (`_agregar_textura_papel`, std ≈ 6) para que sigan representando lo que siempre quisieron representar (papel escaneado), y se re-verificó que el CER siguiera en 0.000 tras el cambio (sí).

## Dataset de capturas (`tests/dataset/cu-06/capturas/`)

| Archivo | Qué prueba |
| --- | --- |
| `pagina_web_100.png` | página web a tamaño completo, texto chico (escala de fuente 0.5) |
| `ventana_75.png` | ventana reducida al 75 %, texto más chico todavía (escala 0.38) |
| `pagina_web_jpg_comprimido.jpg` | la misma página web, re-codificada JPEG calidad 35 (artefactos de compresión) |

`respuestas_capturas.json`: texto esperado de las 3. Meta informativa (no es PP-05): CER ≤ 10 %.

## Hallazgo: el OSD de Tesseract no es confiable en recortes chicos de interfaz

Al correr `pagina_web_100.png` por el pipeline completo, el resultado fue confianza 0 (nada reconocido); la versión JPEG dio texto con apariencia de volteado ("pepilgejuog ap ¡eyod..."). Diagnóstico: el propio OSD de Tesseract reportaba **180°** sobre una imagen perfectamente derecha (confirmado probando la misma imagen sin pasar por `corregir_orientacion`: ahí sí se reconocía bien). Una captura de pantalla, a diferencia de una foto o un escaneo, **nunca viene rotada en la práctica** -- así que `procesar_imagen_captura` dejó de llamar al OSD en absoluto. Con ese cambio, las 3 capturas pasaron a CER 0.000.

## Antes / después (misma imagen: `pagina_web_100.png`)

```python
from ocr.motor import procesar_imagen, procesar_imagen_captura
# misma imagen decodificada para ambas llamadas

# ANTES (Bloque 1-4: procesar_imagen, sin detección de capturas)
#   confianza_media=40.9   segundos=1.80
#   texto='"sejensuew seytodes sns eynsuco apand by\nPepIIgejuo ap euod je
#          opuesuatg\nepnAy 194 JEYP3 CALCIY'   (OSD también confundido acá)

# DESPUÉS (Bloque 2b: procesar_imagen_captura)
#   confianza_media=96.0   segundos=0.72
#   texto='Archivo Editar Ver Ayuda\nBienvenido al portal de Contabilidad\n
#          Aqui puede consultar sus reportes mensuales.'
```

Con el umbral `OCR_PAGINA_ILEGIBLE=50` de antes, el resultado "antes" (confianza 40.9) se habría informado ilegible -- no se habría inventado texto (PP-06 seguía cumpliéndose), pero una captura perfectamente legible se habría descartado por completo. El Bloque 2b no corrige un caso de "texto inventado": corrige un caso de "se tira algo que sí se podía leer".

## Medición completa (dataset real, Tesseract real, dentro del worker)

```
legible_render_limpio.png   CER=0.000  (sin cambios respecto al Bloque 4)
legible_perspectiva.png     CER=0.000  (sin cambios)
legible_rotada_90.png       CER=0.000  (sin cambios, OSD sigue en 270°)
pdf_escaneado_2paginas.pdf  CER=0.000 / 0.000  (sin cambios)
baja_calidad_desenfoque.png       -> ilegible (sin cambios)
baja_calidad_bajo_contraste.png   -> ilegible (sin cambios)

pagina_web_100.png              CER=0.000  confianza=96.0%  0.60 s
ventana_75.png                  CER=0.000  confianza=94.7%  0.69 s
pagina_web_jpg_comprimido.jpg   CER=0.000  confianza=96.0%  0.59 s

10 passed in 35.11 s
```

```
tests/unit (suite completa, con los cambios de este bloque): 409 passed
ruff check src tests: sin hallazgos
mypy src/ocr: sin hallazgos (10 archivos)
```

## Pendiente

- Dataset de capturas real (capturas de pantalla de verdad, no renderizadas) -- las 3 de este bloque son sintéticas, igual que el resto del dataset de CU-06.
- La detección "fondo plano" asume que un documento escaneado real tiene algo de textura; una fotocopia extremadamente limpia podría, en teoría, confundirse con una captura -- no se encontró ningún caso así en este dataset, pero tampoco se descartó formalmente.
