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
- ~~El falso positivo de "Agosto" (mayúscula de mes en un título) no se investigó a fondo (por qué el LLM no lo descartó) — se deja anotado para revisar si se repite con más datos.~~ Resuelto en el Bloque O6 (punto 3, más abajo): se agregó una regla determinista que excluye mayúsculas de mes en títulos/encabezados antes de que lleguen al LLM, sin depender de que el LLM lo descarte.

---

# Bloque O6 — Ajuste de CU-05 antes del siguiente sprint (2026-09-28)

Los 5 puntos pedidos, con antes/después medido contra los mismos 5 archivos reales de `tests/dataset/cu-05/` y el LanguageTool/Ollama reales del Bloque O5 (nada simulado). Commits: `3206420` (puntos 1 y 3), `7fe6918` (punto 4), `2d69578` (punto 5).

## Punto 1 — RNF-04: publicar de inmediato, validar dudosos en segundo plano

**Antes (Bloque O5):** `procesar_documento_ortografia` hacía LanguageTool + glosario + la llamada al LLM para los casos dudosos en una sola pasada síncrona -- el análisis no llegaba a `con_hallazgos`/`en_revision` hasta que el LLM respondía. Por eso CU05-01 y CU05-03 tardaban 100.2s/275.5s y no cumplían RNF-04 (límite 60s).

**Después:** `clasificar_segmentos` (fase 1, solo LanguageTool + glosario) persiste de inmediato los hallazgos deterministas (`estado="pendiente"`) y los dudosos (`estado="en_validacion"`) -- el análisis llega a un estado terminal sin esperar al LLM. Una tarea de Celery aparte (`orquestador.tareas.validar_dudosos_ortografia`), encolada justo después, hace la única llamada por lote al LLM y pasa cada dudoso a `"confirmado"` o `"descartado"` (nunca se borra, RNF-06). La UI (`EstadoBadge`, `TarjetaHallazgo`, `Hallazgos.tsx`) muestra "En validación" de inmediato y sondea hasta ver "Confirmado"/"Descartado", sin recargar la página.

Verificado en vivo, end-to-end, con LanguageTool y Ollama reales (`src/ui/e2e/cu05-validacion-en-segundo-plano.spec.ts`, Playwright + Chromium real):

| | Antes (O5) | Después (O6) |
| --- | --- | --- |
| El análisis llega a "Con hallazgos" | Solo después de que el LLM responde (100-275s) | En 8-20s, sin esperar al LLM |
| Estado del hallazgo dudoso mientras el LLM trabaja | No existía -- no había hallazgo visible todavía | "En validación", visible de inmediato, sin botones Aceptar/Rechazar |
| Qué ve el usuario al terminar el LLM | Nada distinto (ya estaba esperando desde el inicio) | "Confirmado"/"Descartado" aparece solo, sin recargar (sondeo cada 5s) |

Se encontró y corrigió en esta misma verificación en vivo un fallo real: si `sesion.rollback()`/`commit()` del manejo de errores de la fase 2 fallaban también (Postgres inestable bajo la misma presión de memoria documentada en `local-S1.md`), la excepción se propagaba sin control y reventaba la tarea de Celery. Ahora se captura, se registra en el log del worker, y el hallazgo simplemente queda "en_validacion" (con rastro) en vez de perderse.

## Punto 2 — llama3.2:3b vs gpt-oss:20b para validar dudosos

Medido con los 5 archivos reales, en el mismo hardware sin GPU, cada uno en una corrida propia (sin contención de otro proceso pesado corriendo al mismo tiempo):

| Archivo | gpt-oss:20b (recall / FP / tiempo) | llama3.2:3b (recall / FP / tiempo) |
| --- | --- | --- |
| CU05-01 .docx | 9/9, 0 FP, 194.5s | 8/9, 0 FP, 25.6s |
| CU05-02 .pptx | 4/5, 0 FP, 1.1s | 4/5, 0 FP, 2.8s |
| CU05-03 .pdf | 5/5, 0 FP, 291.5s | 3/5, 0 FP, 45.4s |
| CU05-04 .xlsx | 3/3, 0 FP, 6.0s | 3/3, 0 FP, 4.3s |
| CU05-05 .txt | 2/2, 0 FP, 0.1s | 2/2, 0 FP, 0.4s |
| **Global** | **recall 95.8% (23/24), FP 0%** | **recall 83.3% (20/24), FP 0%** |

(pptx/xlsx/txt no tienen ningún caso dudoso en este dataset -- el tiempo ahí es solo LanguageTool, sin llamada al LLM; la comparación de modelos aplica de verdad solo a docx y pdf.)

**Sobre el falso positivo "Agosto":** con la regla del punto 3 ya activa, "Agosto" se excluye antes de convertirse en candidato dudoso -- ni gpt-oss:20b ni llama3.2:3b llegan a verlo, así que ambos quedan en 0% FP. El criterio original de este punto ("¿lo descarta el LLM?") quedó resuelto por una regla determinista, no por ninguno de los dos modelos.

**Decisión:** llama3.2:3b es 4-7x más rápido, pero su recall (83.3%) queda por debajo del umbral de PP-03 (≥ 90%) -- confirma 8/9 y 3/5 en vez de 9/9 y 5/5, es decir, deja pasar como "no es error" casos que sí lo eran. No es "igual o mejor" que gpt-oss:20b, así que **se mantiene gpt-oss:20b** (`LLM_MODEL_PRINCIPAL`) también para esta tarea. `LLM_MODEL_ORTOGRAFIA` queda soportado en el código (`orquestador/tareas.py::validar_dudosos_ortografia`) y documentado en `.env.local.example`, pero sin valor por defecto -- cae a `LLM_MODEL_PRINCIPAL`. Con RNF-04 sin cumplirse en docx/pdf con dudosos en este hardware, la prioridad fue no sacrificar recall por velocidad; re-evaluar si hay GPU disponible (ADR-005).

## Punto 3 — Regla propia: mayúscula de mes en títulos/encabezados

Confirmado contra LanguageTool real: la regla es `MIN_MESES` (categoría `CASING`, `grammar.xml`). Se agregó `_es_mes_en_titulo_o_encabezado` en `ortografia/revision.py`, que excluye una coincidencia `MIN_MESES` cuando la ubicación es un título/encabezado (`Párrafo 0`, `Página 1, bloque 1`, `Encabezado *`, `Pie de página *`, `Diapositiva *, título`) -- antes de clasificarla como determinista o dudosa.

| | Antes (O5) | Después (O6) |
| --- | --- | --- |
| Falsos positivos globales | 4.2% (1/24) -- "Agosto" en el título del PDF | **0% (0/23, con gpt-oss:20b) / 0% (0/20, con llama3.2:3b)** |

## Punto 4 — PP-04 real para .xlsx y texto plano

Extendido `tests/integration/test_cu05_pp03_pp04.py` con datos reales (antes solo docx/pptx):

| Formato | Verificación | Resultado |
| --- | --- | --- |
| .xlsx (CU05-04) | La hoja, sus dimensiones (A1:C6) y las celdas que ninguna corrección tocó (encabezado, códigos de cuenta) quedan intactas | PASSED |
| Texto plano (CU05-05) | El texto corregido reemplaza justo los errores detectados y deja el resto (incluido el término de glosario "SFC") intacto | PASSED |

El PDF sigue cubierto solo con datos sintéticos del Bloque O3 (siempre genera un .docx nuevo, RF-14 -- no hay "PDF corregido" que verificar).

## Punto 5 — .gitignore y auditoría de secretos en git

- Se agregó `Claude outputs/` a `.gitignore` (carpeta de trabajo local de la herramienta de asistencia, nunca contenido del proyecto).
- Auditoría del historial completo (`git log -p --all`, previo a este bloque, 37 commits) buscando claves/API keys/contraseñas/tokens reales y archivos de credenciales (`.pem`/`.key`/`.env` real, etc.): **no se encontró ningún secreto real**. Los únicos `.env*` agregados alguna vez son las plantillas `.example`; toda referencia a contraseñas/claves en el código son `os.environ.get(...)`, valores de prueba explícitos (`"clave-de-prueba"`, `"dev-local-solo-desarrollo"`), o placeholders `[POR CONFIRMAR]` en los `.example`.

## Pruebas y verificación (Bloque O6)

```
tests/unit: 155 passed
tests/integration/test_cu05_pp03_pp04.py: 10/10 casos passed (con gpt-oss:20b,
  configuración final) -- medidos en corridas dedicadas por archivo, no en una
  sola invocación conjunta: correr los 10 casos + la suite unitaria a la vez
  sobrecargó el host (mismo tipo de contención de memoria/CPU documentado en
  local-S1.md) e hizo que LanguageTool mismo diera timeout una vez en el PDF
  -- no es un defecto del código, es la misma limitación de hardware conocida.
src/ui (vitest): 37 passed
src/ui (tsc --noEmit / oxlint): sin errores (2 warnings preexistentes, no relacionados)
ruff / mypy (src completo): sin hallazgos
e2e/cu05-validacion-en-segundo-plano.spec.ts: 1 passed (Playwright + Chromium real, LanguageTool + Ollama reales)
```
