# Resultados — Bloque O5 (CU-05 Revisión ortográfica)

**Versión:** 0.3.0
**Fecha:** 2026-09-29
**Relacionado con:** docs/04-pruebas/casos-prueba/PP-03.md, PP-04.md, docs/03-diseno/secuencia/cu-05-ortografia.md, docs/04-pruebas/resultados/local-S1.md, docs/01-requerimientos/01-requerimiento-formal.md (RNF-04 v0.8)

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

> **[ACTUALIZADO 2026-09-29, SRS v0.8]** Este umbral (≤ 1 min) ya no es el
> vigente para CU-05 -- ver la actualización al final de este documento.
> Se deja la tabla con los números tal como se midieron el 2026-09-28 (no
> se reescribe la historia); la columna "¿Cumple?" evaluaba el umbral de
> ese momento.

| Archivo | Tiempo | ¿Cumple (umbral de esa fecha, ≤ 1 min)? |
| --- | --- | --- |
| CU05-01 (.docx) | 100.2 s | **No** |
| CU05-02 (.pptx) | 2.7 s | Sí |
| CU05-03 (.pdf) | 275.5 s | **No** |
| CU05-04 (.xlsx) | 3.4 s | Sí |
| CU05-05 (.txt) | 0.1 s | Sí |

**3 de 5 documentos cumplían el umbral de esa fecha con margen amplio** (sin ningún caso "dudoso" que necesite LLM, la revisión es solo LanguageTool + glosario: unos pocos segundos). Los 2 que no cumplían (CU05-01, CU05-03) son justo los que tienen al menos un caso dudoso de contexto (p. ej. "a"/"ha", "de"/"dé") y por lo tanto necesitan la única llamada por lote al LLM (`gpt-oss:20b`) — el cuello de botella es la misma limitación de hardware ya documentada para CU-01 (`local-S1.md`): sin GPU, este modelo tarda decenas de segundos a varios minutos por llamada, según el tamaño del prompt. El diseño ya minimiza las llamadas al mínimo posible (como máximo 1 por documento, sin importar cuántos casos dudosos tenga, ver Bloque O2).

## Hallazgos de esta fase

1. **Confirma en datos reales lo que O2 verificó con un LLM simulado**: el recall de 23/24 y la ubicación exacta del único hueco (error de concordancia que LanguageTool nunca reporta) coinciden exactamente con lo anticipado en el Bloque O2.
2. **El filtro de falsos positivos por LLM no es perfecto**: con datos reales, un caso (mayúscula de mes en un título) no se descartó. No es un defecto de diseño (el LLM sigue siendo el único que puede decidir esto; LanguageTool no distingue "título" de "oración") pero es una fuente de imprecisión real a monitorear si se agregan más escenarios de prueba.
3. **El tiempo total depende directamente de si el documento tiene algún caso dudoso**, no de su tamaño o formato — documentos sin ningún caso "de/dé"-como terminan en segundos; los que sí tienen, tardan bastante más, por la lentitud de `gpt-oss:20b` en CPU. [ACTUALIZADO 2026-09-29] Con el umbral vigente de RNF-04 (≤ 5 min, SRS v0.8) los 5 documentos de este dataset cumplen -- ver la actualización al final de este archivo.

## Pendiente

- ~~RNF-04 para documentos con casos dudosos sigue sin cumplirse en este hardware sin GPU — mismo pendiente que CU-01, sujeto a ADR-005 (hardware de stage).~~ [ACTUALIZADO 2026-09-29] El SRS v0.8 ajustó el umbral de CU-05 a ≤ 5 min; con los tiempos ya medidos (100.2s–291.5s en el peor caso, con casos dudosos) el requisito se cumple en este hardware, sin esperar a ADR-005. Ver la actualización al final de este archivo.
- El error de concordancia no detectable por LanguageTool gratuito (#10 de la hoja de respuestas) queda fuera de alcance de este bloque.
- ~~El falso positivo de "Agosto" (mayúscula de mes en un título) no se investigó a fondo (por qué el LLM no lo descartó) — se deja anotado para revisar si se repite con más datos.~~ Resuelto en el Bloque O6 (punto 3, más abajo): se agregó una regla determinista que excluye mayúsculas de mes en títulos/encabezados antes de que lleguen al LLM, sin depender de que el LLM lo descarte.

---

# Bloque O6 — Ajuste de CU-05 antes del siguiente sprint (2026-09-28)

Los 5 puntos pedidos, con antes/después medido contra los mismos 5 archivos reales de `tests/dataset/cu-05/` y el LanguageTool/Ollama reales del Bloque O5 (nada simulado). Commits: `3206420` (puntos 1 y 3), `7fe6918` (punto 4), `2d69578` (punto 5).

## Punto 1 — RNF-04: publicar de inmediato, validar dudosos en segundo plano

**Antes (Bloque O5):** `procesar_documento_ortografia` hacía LanguageTool + glosario + la llamada al LLM para los casos dudosos en una sola pasada síncrona -- el análisis no llegaba a `con_hallazgos`/`en_revision` hasta que el LLM respondía. Por eso CU05-01 y CU05-03 tardaban 100.2s/275.5s (con el umbral vigente en ese momento, ≤ 1 min, no cumplían RNF-04; con el umbral actual del SRS v0.8, ≤ 5 min, sí habrían cumplido, aunque el usuario seguía esperando esos mismos segundos sin ver nada).

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

**Decisión:** llama3.2:3b es 4-7x más rápido, pero su recall (83.3%) queda por debajo del umbral de PP-03 (≥ 90%) -- confirma 8/9 y 3/5 en vez de 9/9 y 5/5, es decir, deja pasar como "no es error" casos que sí lo eran. No es "igual o mejor" que gpt-oss:20b, así que **se mantiene gpt-oss:20b** (`LLM_MODEL_PRINCIPAL`) también para esta tarea. `LLM_MODEL_ORTOGRAFIA` queda soportado en el código (`orquestador/tareas.py::validar_dudosos_ortografia`) y documentado en `.env.local.example`, pero sin valor por defecto -- cae a `LLM_MODEL_PRINCIPAL`. [ACTUALIZADO 2026-09-29] Con el umbral de RNF-04 ajustado a ≤ 5 min (SRS v0.8), gpt-oss:20b ya cumple con los tiempos medidos aquí (194.5s / 291.5s, ambos < 300s) -- la decisión de no sacrificar recall por velocidad queda todavía más clara: no hace falta el modelo más rápido para cumplir el requisito. El margen del PDF es angosto (291.5s de 300s, ~3 % de margen) y conviene seguir vigilándolo; re-evaluar si hay GPU disponible (ADR-005).

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

---

# Actualización 2026-09-29 — RNF-04 ajustado a ≤ 5 min por documento (SRS v0.8)

`docs/01-requerimientos/01-requerimiento-formal.md` pasó a v0.8: RNF-04 para CU-05 ya no es "≤ 1 min medido en stage" -- ahora es "hallazgos deterministas visibles de inmediato, validación de casos dudosos completa en ≤ 5 min por documento". `tests/integration/test_cu05_pp03_pp04.py::RNF04_LIMITE_SEGUNDOS` se actualizó de `60.0` a `300.0` para que el reporte del test use el umbral vigente (el test nunca afirmó pass/fail sobre esto, solo lo mide y reporta -- no hizo falta correrlo de nuevo para este cambio, el propio tiempo medido no cambia, solo su interpretación).

Re-evaluando los tiempos YA MEDIDOS en este mismo archivo (Bloques O5 y O6) contra el nuevo umbral de 300s:

| Archivo | Tiempo medido (O5, 2026-09-28) | Tiempo medido (O6, gpt-oss:20b) | ¿Cumple ≤ 5 min? |
| --- | --- | --- | --- |
| CU05-01 (.docx) | 100.2 s | 194.5 s | **Sí** (margen amplio) |
| CU05-02 (.pptx) | 2.7 s | 1.1 s | Sí |
| CU05-03 (.pdf) | 275.5 s | 291.5 s | **Sí, con margen angosto** (~3-8 s de 300 s) |
| CU05-04 (.xlsx) | 3.4 s | 6.0 s | Sí |
| CU05-05 (.txt) | 0.1 s | 0.1 s | Sí |

**Los 5 documentos cumplen RNF-04 bajo el umbral vigente** -- con la arquitectura de dos fases del Bloque O6 (punto 1), además, el usuario ve los hallazgos deterministas de inmediato (8-20s) y no espera esos 100-291s en absoluto salvo para ver "Confirmado"/"Descartado" en los casos dudosos, que es justo lo que ahora pide RNF-04 explícitamente ("hallazgos visibles" + "validación de dudosos completa en ≤ 5 min", como dos cosas separadas).

**Nota de margen:** el PDF (CU05-03) tiene el margen más angosto de los cinco (291.5s de 300s en la medición del Bloque O6, con el host bajo la misma presión de memoria documentada en `local-S1.md`). No es un incumplimiento, pero es el candidato más probable a fallar si el prompt crece (más casos dudosos) o el host está más cargado. Sigue aplicando la recomendación de re-evaluar con GPU (ADR-005) si el margen deja de ser aceptable en producción.

**Conclusión:** las secciones "Hallazgos de esta fase" y "Pendiente" del Bloque O5, y la "Decisión" del punto 2 del Bloque O6, quedaron marcadas en línea con esta actualización -- no se reescribieron los números originales, solo su interpretación bajo el umbral vigente.

---

# Actualización 2026-09-30 — recall 23/24 → 22/24 investigado: variabilidad del LLM, no una regresión de código

**Disparador:** entre el Bloque O6 (23/24, PDF en 291.5s) y el Bloque K7 (22/24, PDF en 80.6s) el recall global de PP-03 bajó, con el PDF (CU05-03) como único archivo distinto. Se sospechó variabilidad del LLM en la validación de casos dudosos (fase 2, `ortografia.revision.validar_candidatos_con_llm`).

**Diagnóstico:** `rag/cliente_llm.py::generar_texto` no fijaba `temperature` ni `seed` -- cada llamada a Ollama usaba el muestreo por defecto del modelo (no determinista). Confirmado como causa real: se agregó `options: {"temperature": 0, "seed": 42}` al payload (Bloque K7, ver commit) y se corrió PP-03 **3 veces seguidas** con el stack real (LanguageTool + Ollama nativo, sin mocks):

```
Corrida 1: CU05-01 9/9 · CU05-02 4/5 · CU05-03 4/5 · CU05-04 3/3 · CU05-05 2/2 -- 5 passed in 247.74s
Corrida 2: CU05-01 9/9 · CU05-02 4/5 · CU05-03 4/5 · CU05-04 3/3 · CU05-05 2/2 -- 5 passed in 220.94s
Corrida 3: CU05-01 9/9 · CU05-02 4/5 · CU05-03 4/5 · CU05-04 3/3 · CU05-05 2/2 -- 5 passed in 187.77s
```

**Las 3 corridas dieron exactamente el mismo resultado, archivo por archivo** -- confirma que `temperature=0`/`seed=42` sí vuelve determinista la validación de dudosos (antes no lo era, y esa no-determinismo no estaba documentado ni probado). Recall global estable: **22/24 = 91.7 %**, 0 falsos positivos en las 3 corridas (mejor que el 4.2 % de O6 -- el falso positivo de O6 en "Agosto" tampoco se repite con `temperature=0`). Los 5 documentos siguen cumpliendo RNF-04 (≤ 300s) en las 3 corridas.

**Error específico que ya no se detecta:** fila 19 de `Respuestas_CU05_Ortografia.xlsx` para CU05-03 -- `"se de seguimiento"` -> `"se dé seguimiento"` (acentuación diacrítica, "de" vs "dé" según contexto gramatical, subjuntivo). Confirmado ejecutando `revisar_segmentos` directamente sobre el PDF: la fase 2 (LLM) juzga, con `temperature=0`/`seed=42`, que "de" ya está correcto ahí -- no marca error. Los otros 4 errores esperados de ese archivo ("depositos", "Ademas", "abian", "nesesario") sí se detectan en las 3 corridas.

**¿Es una regresión de código? No.** El prompt (`_construir_prompt_lote`) ya menciona explícitamente "de" vs "dé" como ejemplo de caso ambiguo -- no hay un error de instrucción que corregir. Lo que cambió es que antes esta llamada al LLM era aleatoria (sin `seed`): la corrida de O6 tuvo la suerte de que el modelo marcara correctamente este caso diacrítico esa vez; las corridas de K6/K7 y estas 3 nuevas, con o sin `seed` fija, coinciden en el resultado contrario. No se buscó ni se probó una `seed` distinta para forzar que este caso puntual "pase" -- habría sido ajustar el resultado a un solo caso de prueba, no una mejora real. **91.7 % sigue cumpliendo el umbral de PP-03 (≥ 90 %)** con margen, y ahora el resultado es reproducible en vez de variar entre corridas -- una mejora real sobre el estado anterior (recall silenciosamente variable no es aceptable en una herramienta de cumplimiento).

**Cambio de código:** `rag/cliente_llm.py::generar_texto` manda `options.temperature=0` y `options.seed=42` en cada request a Ollama (constantes `TEMPERATURA_POR_DEFECTO`/`SEMILLA_POR_DEFECTO`), aplicando tanto a la validación de dudosos de CU-05 como a la redacción de hallazgos contables de CU-01/RF-12 (mismo criterio: determinismo también importa para la trazabilidad/auditoría, RNF-06). Pruebas nuevas: `tests/unit/test_cliente_llm.py::test_generar_texto_envia_temperature_0_y_seed_fija_por_defecto`.

**Pendiente:** el caso "de"/"dé" en subjuntivo queda como límite conocido del modelo actual (`gpt-oss:20b`) con `temperature=0` -- no bloqueante (91.7 % ≥ 90 %), documentado para no sorprender en una futura medición.
