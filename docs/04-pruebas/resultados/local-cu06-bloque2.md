# Resultados — CU-06 "OCR imagen/PDF escaneado a texto", Bloque 2 (Calidad sin inventar)

**Versión:** 0.1.0
**Fecha:** 2026-10-08
**Relacionado con:** docs/04-pruebas/resultados/local-cu06-bloque1.md, docs/05-prompts/P-09, P-11-cu06-ocr-mvp.md, RN-06, PP-05, PP-06

## Alcance

Umbrales de confianza configurables, páginas ilegibles sin texto inventado (documento completo ilegible completa el análisis con aviso, no falla), y palabras dudosas como `Hallazgo` individual con sugerencia opcional de LanguageTool (nunca autocorrige; excluye tokens con dígitos y términos del glosario). Sin interfaz todavía (Bloque 3).

## Backend

| Ruta | Cambio | Prueba | Métrica |
| --- | --- | --- | --- |
| `.env.example`, `.env.local.example`, `.env.stage.example`, `.env.local` | `OCR_CONF_DUDOSA=60`, `OCR_CONF_REVISAR=80`, `OCR_PAGINA_ILEGIBLE=50`; resuelto `OCR_DPI_MINIMO=300` (ya no "[POR CONFIRMAR]" -- coincide con la constante ya usada en `ocr.preprocesamiento`) | — | — |
| `src/ocr/calidad.py` (nuevo) | `Umbrales` (+ `umbrales_desde_entorno`), `clasificar_confianza` (dudosa/revisar/ok), `es_pagina_ilegible` (nunca para texto nativo; ilegible si no hay palabras o la confianza media no alcanza el umbral) | `tests/unit/test_ocr_calidad.py` (12 casos) | 12 passed en 0.11 s; cobertura 100 % |
| `src/ocr/hallazgos.py` (nuevo) | `detectar_palabras_dudosas`: una `PalabraDudosa` por palabra bajo `OCR_CONF_REVISAR` en páginas legibles; sugerencia opcional de LanguageTool sobre el texto de la línea (contexto), excluyendo coincidencias con dígitos o del glosario; nunca sustituye el texto reconocido | `tests/unit/test_ocr_hallazgos.py` (9 casos: niveles, texto nativo, página ilegible, sugerencia asociada, exclusión por dígito, exclusión por glosario, no-autocorrección) | 9 passed en 0.19 s; cobertura 97 % |
| `src/orquestador/orquestador/pipeline_ocr.py` | Página ilegible publica un aviso (`[Página N: ilegible...]`) en vez de su texto; si TODAS las páginas de OCR son ilegibles, un único `Hallazgo` de aviso (severidad "alta", ubicación "Documento completo"); si no, una `Hallazgo` por palabra dudosa (severidad "alta"/"media" según nivel, `texto_original`/`correccion_sugerida`) | `tests/unit/test_pipeline_ocr.py` (+2 casos: página ilegible, palabra dudosa persistida) | 4 passed en 10.91 s; cobertura 100 % |
| `src/orquestador/orquestador/tareas.py` | Rama "ocr" ahora desempaqueta `(hallazgos, páginas)`; nuevo parámetro `glosario_ocr`; `analizar_documento` inyecta `cargar_glosario()` real | `tests/unit/test_orquestador_tareas.py` (+1 caso: página ilegible extremo a extremo con `moto`, estado `con_hallazgos`) | 4 passed en 6.66 s |

```
tests/unit (suite completa): 375 passed en 76.66 s
ruff check src tests: sin hallazgos
mypy src: sin hallazgos (10 archivos)
```

### Verificación con Tesseract real (Docker, sin fakes de confianza)

Mismo build del Bloque 1 (sin cambios de Dockerfile: `calidad.py`/`hallazgos.py` no agregan dependencias). Dos imágenes sintéticas dentro del contenedor:

```
Imagen clara ("Factura Q 1,250.00 autorizada"):
  texto reconocido: 'Factura Q 1,250.00 autorizada'
  confianza media:  94.5
  ilegible:         False
  palabras dudosas: []

Imagen con desenfoque + ruido fuerte (simula foto de baja calidad):
  texto reconocido: '' (Tesseract no reconoció nada)
  confianza media:  0.0
  ilegible:         True
```

Confirma PP-06 con el motor real: ante una imagen genuinamente ilegible, Tesseract no devuelve texto y `es_pagina_ilegible` lo detecta -- cero texto inventado, no un reconocimiento erróneo disfrazado de resultado.

## Hallazgos de este bloque

1. **El umbral de página ilegible puede disparar con una sola palabra de baja confianza**: si una página tiene pocas palabras, una sola dudosa puede arrastrar la confianza media por debajo de `OCR_PAGINA_ILEGIBLE`. Es el comportamiento esperado (RN-06: ante la duda, no publicar), pero quedó documentado para no sorprender en el Bloque 4 al medir con el dataset real.
2. **La sugerencia de LanguageTool se asocia por offset dentro de la línea, no por palabra suelta**: se corre LT sobre la línea completa (le da contexto gramatical) y luego se mapea la coincidencia a la palabra de Tesseract que solapa en posición -- mismo tipo de correlación por offset que ya usa `validadores/redaccion/correccion_ortografica.py`, pero aplicada a dos fuentes de offsets distintas (palabras de Tesseract vs. coincidencias de LT) en vez de una sola.

## Pendiente (antes del Bloque 3)

- Interfaz "Imagen a texto": vista lado a lado, resaltado rojo/amarillo, edición manual, descargas .txt/.docx, botones "Revisar ortografía"/"Mejorar redacción".
- Las métricas PP-05 (CER ≤5 %)/PP-06 formales siguen pendientes del dataset real de `tests/dataset/cu-06/` (Bloque 4) -- las de hoy son de humo (dos imágenes sintéticas).
