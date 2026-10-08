# Resultados — CU-06 "OCR imagen/PDF escaneado a texto", Bloque 3 (Interfaz básica)

**Versión:** 0.1.0
**Fecha:** 2026-10-08
**Relacionado con:** docs/04-pruebas/resultados/local-cu06-bloque1.md, local-cu06-bloque2.md, docs/05-prompts/P-11-cu06-ocr-mvp.md

## Alcance

Opción "Imagen a texto" en Nuevo análisis (uno o varios archivos), vista lado a lado imagen | texto con palabras dudosas resaltadas, edición manual, botón Copiar, descargas .txt/.docx (con dudosas resaltadas), botones para encadenar a CU-05/CU-02, y bitácora de archivo/páginas/confianza/ilegibles/ediciones/descargas. Sin dataset ni métricas PP-05/PP-06 formales todavía (Bloque 4).

## Backend

| Ruta | Cambio | Prueba | Métrica |
| --- | --- | --- | --- |
| `src/ocr/exportar_docx.py` (nuevo) | `construir_docx_resaltado`: texto exacto reconocido + resaltado rojo/amarillo por coincidencia de texto (python-docx, `WD_COLOR_INDEX`) | `tests/unit/test_ocr_exportar_docx.py` (4 casos) | 4 passed; cobertura 100 % |
| `src/api/esquemas.py` | `SolicitudEditarTextoOcr`, `RespuestaEditarTextoOcr` | — | — |
| `src/api/main.py` | `GET /documentos/{id}/version-original` (nuevo: servía solo la corregida, nunca el original); `PUT /documentos/{id}/texto-ocr` (edición manual, sobrescribe el mismo objeto S3); `GET /documentos/{id}/ocr-docx` (genera el .docx al vuelo); bitácora `ocr_descarga_txt` agregada a `version-corregida` (solo cuando el análisis es "ocr", aditivo, no afecta a CU-01/CU-05) | `tests/unit/test_api_ocr.py` (6 casos) | 6 passed en 15.23 s |
| `src/orquestador/orquestador/pipeline_ocr.py` | `resumen_paginas()`: línea de bitácora "N página(s), confianza media X%, N ilegible(s)" | `tests/unit/test_pipeline_ocr.py` (+2 casos) | 6 passed en 11.43 s; cobertura 100 % |
| `src/orquestador/orquestador/tareas.py` | Registra `ocr_completado` con el resumen apenas termina el motor (antes de los demás, Bloque 4 no lo necesita pero ya queda disponible en vivo) | `tests/unit/test_orquestador_tareas.py` (+1 aserción) | 4 passed |
| `src/api/Dockerfile` | `COPY ocr ./ocr` -- la API genera el .docx de forma síncrona con `ocr.exportar_docx` (solo `python-docx`, ya presente vía `parsers/requirements.txt`); el resto de `ocr` (OpenCV/Tesseract) nunca se importa desde la API | build Docker real (ver abajo) | — |

```
tests/unit (suite completa): 387 passed en 90.97 s
ruff check src tests: sin hallazgos
mypy src: sin hallazgos (31 archivos)
```

## Frontend

| Ruta | Cambio | Prueba |
| --- | --- | --- |
| `src/ui/src/paginas/NuevoAnalisis.tsx` | "Imagen a texto" habilitado (antes "OCR (próximamente)"); extensiones png/jpg/jpeg/tiff/bmp/pdf; selección de varios archivos solo para OCR -- sin soporte de "un análisis con N documentos" en el modelo de datos, así que N archivos crean N análisis independientes, con "Archivo N de M" durante la subida y un mensaje final que remite al panel de análisis recientes | sin prueba dedicada (tampoco la tenía antes de este bloque) |
| `src/ui/src/paginas/ResultadoOcr.tsx` (nuevo) | Vista lado a lado (imagen real vía `<img>`/PDF vía `<embed>`, descargados con el token de auth -- no hay forma de poner el header `Authorization` en un `<img src>` directo); texto con palabras dudosas resaltadas (`<mark>` rojo/amarillo, mismo criterio de color que `SeveridadBadge`); edición manual + Guardar (`PUT /texto-ocr`); Copiar; descargas .txt/.docx; botones "Revisar ortografía"/"Mejorar redacción" (reutilizan `subirDocumento` con el texto actual envuelto en un `.txt`, el mismo truco que ya usa "pegar texto" en CU-02/CU-05 -- sin endpoint nuevo de "encadenar") | `tests/unit/ResultadoOcr.test.tsx` (8 casos) |
| `src/ui/src/paginas/Hallazgos.tsx` | Delega a `ResultadoOcr` cuando `tipo_revision === "ocr"` (mismo patrón que ya existía para "redaccion") | cubierta indirectamente por `ResultadoOcr.test.tsx` |
| `src/ui/src/paginas/AgenteTrabajando.tsx` | Ahora muestra `entrada.detalle` de cada paso de bitácora (antes solo la etiqueta) + etiqueta "OCR completado" -- mejora genérica, no solo para OCR, que de paso satisface "progreso" sin inventar un mecanismo de avance por página que el backend no tiene | sin prueba dedicada (tampoco la tenía antes) |

```
npx tsc -b: sin errores
npx vitest run: 60 passed (11 archivos)
npm run lint (oxlint): sin hallazgos nuevos (2 warnings preexistentes, no relacionados)
```

## Decisiones de alcance que requieren tu visto bueno

1. **"Progreso 'Página N de M'" no es un contador en vivo por página.** El motor no reporta avance incremental dentro de un documento (correrlo requeriría instrumentar Celery con callbacks de progreso, fuera del alcance de una "interfaz básica"). Lo que sí hay: (a) "Archivo N de M" real y en vivo durante la subida de varios archivos, y (b) el resumen `ocr_completado` ("N página(s), confianza media X%, N ilegible(s)") aparece en la pantalla "Agente trabajando" apenas el motor termina, vía el mecanismo de bitácora que esa pantalla ya tenía. No hay conteo de páginas mientras el motor corre.
2. **"Uno o varios archivos" crea N análisis independientes, no un análisis con N documentos.** El modelo de datos es 1 `Documento` : 1 `Analisis` en todo el sistema (confirmado para los otros tres tipos de revisión también); cambiarlo habría sido una migración de esquema fuera de "interfaz básica". Con varios archivos, la pantalla se queda en "Nuevo análisis" y actualiza el panel de análisis recientes en vez de navegar a un resultado único.
3. **El resaltado de palabras dudosas es por coincidencia exacta de texto, no por posición.** Tanto en pantalla como en el .docx: si la misma palabra aparece dos veces (una dudosa, otra no), ambas quedan resaltadas. Documentado también en el docstring de `ocr.exportar_docx`.

## Verificación extremo a extremo (stack real, sin mocks)

Se levantó el stack completo (`docker compose ... up -d --build postgres redis localstack languagetool api orquestador worker`) con las imágenes reconstruidas de este bloque, y se probó el flujo real por HTTP (login real, Postgres real, LocalStack real, Tesseract real, LanguageTool real):

```
1. Subida de una imagen PNG con texto real ("Factura Q 1,250.00 / Proveedor: Acme S.A.")
   con tipo_revision=ocr -> analisis_id creado, estado "cargado".
2. Worker procesa -> estado "en_revision" en ~7s.
3. Bitácora: analisis_iniciado -> ocr_completado ("1 página(s), confianza media 93%,
   0 ilegible(s)") -> analisis_completado.
4. GET /documentos/{id}/version-original -> 200, image/png, bytes IDÉNTICOS al
   archivo subido (diff sin salida).
5. GET /documentos/{id}/version-corregida -> "Factura Q 1,250.00\nProveedor: Acme S.A,"
   (texto real reconocido por Tesseract, cifras intactas).
6. PUT /documentos/{id}/texto-ocr {"texto": "...editado a mano"} -> {"guardado": true};
   GET subsiguiente confirma el nuevo texto.
7. GET /documentos/{id}/ocr-docx -> 200, 36633 bytes; abierto con python-docx,
   el párrafo contiene exactamente el texto editado en el paso 6.
8. Bitácora final: incluye ocr_descarga_txt (x2), ocr_edicion_manual
   ("Texto editado manualmente (35 caracteres)"), ocr_descarga_docx.
9. Encadenado real: el texto de OCR subido como .txt nuevo con tipo_revision=ortografia
   (mismo truco que usa el botón "Revisar ortografía") -> análisis completa con
   2 hallazgos reales de LanguageTool sobre errores sembrados a propósito
   ("heror" -> "héroe"[sic, sugerencia real de LT], "hortografia" -> "ortografía").
```

Esta es la verificación más fuerte posible sin un navegador real disponible en este entorno (no hay herramienta de navegador en esta sesión): confirma que las tres rutas nuevas, la edición, la bitácora y el encadenado funcionan de punta a punta contra la infraestructura real, no solo contra fakes/mocks. Las pruebas de React (`ResultadoOcr.test.tsx`) cubren el renderizado, el resaltado y las interacciones de la UI con el DOM real (jsdom) pero con `fetch` simulado.

## Pendiente (Bloque 4)

- Dataset sintético (`tests/dataset/cu-06/`) y métricas formales PP-05 (CER ≤5 %)/PP-06.
- Medición dentro del contenedor del worker con límites de stage (8 CPU).
- Actualizar plan de pruebas, matriz de trazabilidad, estado del proyecto y guion de demo.
