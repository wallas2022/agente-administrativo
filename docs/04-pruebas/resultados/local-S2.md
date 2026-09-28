# Resultados — Bloque O5 (CU-05 Revisión ortográfica)

**Versión:** 0.1.0
**Fecha:** 2026-09-28
**Relacionado con:** docs/04-pruebas/casos-prueba/PP-03.md, PP-04.md, docs/03-diseno/secuencia/cu-05-ortografia.md, docs/04-pruebas/resultados/local-S1.md

## Alcance

Medición real (sin mocks) de PP-03 (recall y falsos positivos) y PP-04 (preservación de formato del documento corregido) contra el servicio LanguageTool real y el LLM real (`gpt-oss:20b` vía Ollama nativo), usando los 5 documentos de `tests/dataset/cu-05/` y su hoja de respuestas (`Respuestas_CU05_Ortografia.xlsx`, 24 errores sembrados). El glosario se cargó desde `tests/dataset/cu-05/glosario-interno-ejemplo.csv` (SFC, SAT, NIIF, IVA, ISR, DTE, FEL, Banrural), tal como pide este bloque.

Prueba: `tests/integration/test_cu05_pp03_pp04.py` (nueva, formaliza como pytest reproducible lo que `tests/integration/README.md` dejaba pendiente para CU-01 — se salta sola si LanguageTool u Ollama no están arriba). Correr con el stack local levantado:

```
LANGUAGETOOL_HOST=127.0.0.1 LANGUAGETOOL_PORT=8010 LLM_BASE_URL=http://127.0.0.1:11434 \
  .venv/Scripts/python.exe -m pytest tests/integration/test_cu05_pp03_pp04.py -v -s --no-cov
```

## PP-03 — Recall ≥ 90 % y falsos positivos ≤ 10 %

```
8 passed in 396.64s (0:06:36)
```

| Archivo | Esperados detectados | Falsos positivos | Tiempo |
| --- | --- | --- | --- |
| CU05-01_Procedimiento_Cierre_Mensual.docx | 9/9 | 0/9 (0 %) | 100.2 s |
| CU05-02_Resultados_Cierre_Agosto.pptx | 4/5 | 0/4 (0 %) | 2.7 s |
| CU05-03_Informe_Conciliacion_Bancaria.pdf | 5/5 | 1/6 (17 %) | 275.5 s |
| CU05-04_Catalogo_Descripciones.xlsx | 3/3 | 0/3 (0 %) | 3.4 s |
| CU05-05_Texto_para_pegar.txt | 2/2 | 0/2 (0 %) | 0.1 s |
| **Global** | **23/24 = 95.8 %** | **1/24 = 4.2 %** | — |

**Cumple el umbral de PP-03** (recall ≥ 90 %, falsos positivos ≤ 10 %) con margen.

- El único error sembrado no detectado (#10 de la hoja de respuestas, "Indicadores claves" → "Indicadores clave") es un error de **concordancia** que la edición gratuita de LanguageTool no reporta en absoluto para esa frase (verificado también en el Bloque O2: `curl .../v2/check` con esa frase exacta devuelve `matches: []`) — no hay ninguna coincidencia que este código pueda filtrar o clasificar si LanguageTool nunca la marca. Solucionarlo necesitaría LanguageTool Premium o un modelo/regla adicional, fuera del alcance de este bloque.
- El único falso positivo detectado está en el PDF (CU05-03): por el mismo caso ya documentado en el Bloque O2 ("Agosto" en el título "Informe de conciliación bancaria — Agosto 2026", marcado por la regla de mayúsculas de meses). Esta vez, con el LLM real (no un stub que acepta todo), se esperaba que la validación de casos dudosos lo descartara; no lo hizo en esta corrida — con un dataset de 24 errores sembrados, 1 falso positivo real ya dejó la tasa dentro del umbral (4.2 % ≤ 10 %), pero es una señal de que la confirmación del LLM no es perfecta y conviene seguir observándolo con más datos reales.
- Ningún término del glosario (SFC, SAT, NIIF, IVA, ISR, DTE, FEL, Banrural) se marcó como hallazgo en ningún archivo (aserción explícita en la prueba, sin excepciones).

## PP-04 — El documento corregido abre sin error y conserva el formato

```
test_pp04_docx_corregido_conserva_negrita_tabla_y_encabezado PASSED
test_pp04_pptx_corregido_conserva_titulo_vinetas_y_notas PASSED
```

Se aplicaron (como si el Revisor las hubiera aceptado) las correcciones que coincidieron con la hoja de respuestas sobre los archivos originales, y se reabrió el resultado:

- **.docx** (CU05-01): abre sin error, conserva la tabla completa, al menos una corrida en negrita, y el encabezado de página.
- **.pptx** (CU05-02): abre sin error, conserva las 3 diapositivas, el título y las notas del orador.

## RNF-04 — Tiempo ≤ 1 min por documento

| Archivo | Tiempo | ¿Cumple? |
| --- | --- | --- |
| CU05-01 (.docx) | 100.2 s | **No** |
| CU05-02 (.pptx) | 2.7 s | Sí |
| CU05-03 (.pdf) | 275.5 s | **No** |
| CU05-04 (.xlsx) | 3.4 s | Sí |
| CU05-05 (.txt) | 0.1 s | Sí |

**3 de 5 documentos cumplen RNF-04 con margen amplio** (sin ningún caso "dudoso" que necesite LLM, la revisión es solo LanguageTool + glosario: unos pocos segundos). Los 2 que no cumplen (CU05-01, CU05-03) son justo los que tienen al menos un caso dudoso de contexto (p. ej. "a"/"ha", "de"/"dé") y por lo tanto necesitan la única llamada por lote al LLM (`gpt-oss:20b`) — el cuello de botella es la misma limitación de hardware ya documentada para CU-01 (`local-S1.md`): sin GPU, este modelo tarda decenas de segundos a varios minutos por llamada, según el tamaño del prompt. El diseño ya minimiza las llamadas al mínimo posible (como máximo 1 por documento, sin importar cuántos casos dudosos tenga, ver Bloque O2) — reducir más el tiempo requeriría un modelo más liviano o GPU, la misma conclusión [POR CONFIRMAR] pendiente de ADR-005 que ya aplica a CU-01.

## Hallazgos de esta fase

1. **Confirma en datos reales lo que O2 verificó con un LLM simulado**: el recall de 23/24 y la ubicación exacta del único hueco (error de concordancia que LanguageTool nunca reporta) coinciden exactamente con lo anticipado en el Bloque O2.
2. **El filtro de falsos positivos por LLM no es perfecto**: con datos reales, un caso (mayúscula de mes en un título) no se descartó. No es un defecto de diseño (el LLM sigue siendo el único que puede decidir esto; LanguageTool no distingue "título" de "oración") pero es una fuente de imprecisión real a monitorear si se agregan más escenarios de prueba.
3. **RNF-04 depende directamente de si el documento tiene algún caso dudoso**, no de su tamaño o formato — documentos sin ningún caso "de/dé"-como cumplen el límite de sobra; los que sí tienen, no, por la lentitud de `gpt-oss:20b` en CPU.

## Pendiente

- RNF-04 para documentos con casos dudosos sigue sin cumplirse en este hardware sin GPU — mismo pendiente que CU-01, sujeto a ADR-005 (hardware de stage).
- El error de concordancia no detectable por LanguageTool gratuito (#10 de la hoja de respuestas) queda fuera de alcance de este bloque.
- El falso positivo de "Agosto" (mayúscula de mes en un título) no se investigó a fondo (por qué el LLM no lo descartó) — se deja anotado para revisar si se repite con más datos.
