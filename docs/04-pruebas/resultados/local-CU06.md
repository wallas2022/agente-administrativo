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

## Pendiente

- Dataset real/fotografiado (no solo sintético) para una medición de PP-05 con validez más allá del caso base.
- Medición en stage (8 CPU) cuando exista (ADR-005).
- Resto de bloques de CU-11 y otras iteraciones de CU-06 (tablas en imágenes, post-corrección LLM en segundo plano) quedan fuera del alcance de P-11.
