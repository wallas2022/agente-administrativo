# Resultados — Base de conocimiento gobernada (Bloques K0-K7)

**Versión:** 0.2.0
**Fecha:** 2026-09-30
**Relacionado con:** docs/04-pruebas/casos-prueba/PP-07.md, PP-08.md, PP-14.md, PP-20.md · docs/04-pruebas/plan-pruebas-prototipo.md (v0.3) · docs/01-requerimientos/01-requerimiento-formal.md (v0.8) · docs/03-diseno/er/modelo-datos.md · docs/03-diseno/flujos/ingesta-conocimiento.md · docs/04-pruebas/resultados/local-S2.md (CU-05/RNF-04, actualización 2026-09-30)

Cierre de pruebas del Bloque K7 sobre la base de conocimiento gobernada (RF-16, RF-17, CU-08) implementada en K0-K6: modelo de fuentes (K1), importador de plantilla (K2), ingesta de documentos (K3), búsqueda con prioridad y citas separadas (K4), pantalla del curador (K5) y modo offline (K6). Todo lo medido aquí corre contra el stack local real (Postgres, Qdrant, Ollama nativo, LanguageTool) — sin mocks salvo donde se indica explícitamente (S3 vía moto).

Comando de referencia para reproducir el backend completo:
```bash
LANGUAGETOOL_HOST=127.0.0.1 LLM_BASE_URL=http://127.0.0.1:11434 \
    .venv/Scripts/python.exe -m pytest tests/ -q
```

## Bugs reales encontrados y corregidos en este bloque

### 1. Aprobar una v2 dejaba sus propios fragmentos marcados "obsoleta"

Al escribir la prueba de PP-08 se encontró que **aprobar una segunda versión de una fuente podía dejar sus propios fragmentos recién indexados marcados como "obsoleta"**: el endpoint `POST /curaduria/fuentes/{id}/aprobar` (`src/api/main.py`) indexaba la nueva versión y *después* desactivaba los fragmentos de la fuente por `fuente_id` de negocio -- pero v1 y v2 comparten ese mismo `fuente_id` (p. ej. "POL-001"), así que la desactivación apagaba también los puntos que se acababan de indexar como vigentes. El propio test que lo cubría (`test_aprobar_una_segunda_version_obsoletea_la_primera`, Bloque K5) ya documentaba esto como limitación aceptada ("solo importa que no truene").

**Corrección:** invertir el orden -- desactivar los fragmentos de la versión anterior *antes* de indexar los de la nueva (`src/api/main.py`, `aprobar_fuente_endpoint`). Verificado con una aserción nueva que retira los puntos de v2 de Qdrant por su `referencia_vector` real y confirma `estado="vigente"` (antes fallaba con `estado="obsoleta"`).

### 2. `buscar_fragmentos` sin `temperature`/`seed` fijos: recall de PP-03 no reproducible

Investigando por qué el recall de PP-03 bajó de 23/24 (Bloque O6) a 22/24 (Bloque K7), con el PDF (CU05-03) como único archivo distinto: `rag/cliente_llm.py::generar_texto` no fijaba `temperature` ni `seed` en el payload a Ollama, así que la validación de casos dudosos (fase 2 de CU-05, `ortografia.revision.validar_candidatos_con_llm`) no era reproducible entre corridas -- el mismo prompt podía dar resultados distintos. Detalle completo de la investigación, las 3 corridas de confirmación y el error puntual identificado en `docs/04-pruebas/resultados/local-S2.md` (actualización 2026-09-30).

**Corrección:** `generar_texto` manda `options: {"temperature": 0, "seed": 42}` en cada request. Con esto, PP-03 dio el **mismo resultado exacto en 3 corridas seguidas** (22/24 = 91.7 %, 0 FP) -- sigue cumpliendo el umbral (≥ 90 %) y ahora es reproducible, algo que antes no estaba garantizado ni probado.

### 3. Una fuente `referencia` podía no aparecer nunca en las citas

Al medir PP-07 con una muestra que incluía tanto POL-001 (`regla_interna`) como EST-001 (`referencia`), se confirmó que `rag.busqueda.buscar_fragmentos` -- que ordena todos los candidatos por prioridad antes que por similitud -- podía dejar a EST-001 fuera del `top_k` en cualquier consulta, sin importar qué tan relevante fuera, con solo que el área tuviera `>= top_k` fuentes de mayor prioridad. Una fuente tipo `referencia` podía entonces no citarse **nunca**.

**Corrección:** `buscar_fragmentos` ahora busca "referencia" en una consulta aparte a Qdrant (filtrada a ese tipo, top-1, solo si supera `umbral_referencia` -- 0.5 por defecto, similitud coseno) y la agrega al resultado sin quitarle cupo a las reglas. Verificado a nivel unitario (`tests/unit/test_rag.py`) y de integración, con datos reales: la muestra de PP-07 pasó de 100 % solo en el subconjunto de reglas a **100 % en las 12 consultas reales** (reglas + referencias).

## PP-08 — Uso solo de fuentes vigentes

**Umbral:** 0 citas a versiones obsoletas.

```
tests/integration/test_pp07_pp08_pp20_base_conocimiento.py::test_pp08_ninguna_cita_referencia_la_version_obsoleta PASSED
```

Ingesta real de las dos versiones de la misma política (`POL-000_..._OBSOLETA_EJEMPLO.pdf` como v1.0, obsoletada; `POL-001_..._EJEMPLO.pdf` como v2.0, vigente) vía el ciclo de vida real de CU-08 (`curaduria.fuentes.aprobar_fuente` + `curaduria.indexacion.indexar_fuente`, ya con el orden corregido). Se consultó con las 7 secciones reales de v2.0 (contenido casi idéntico al de v1.0, la edición anterior de la misma política -- el caso más exigente posible) y **0 de 7** citas referenciaron `version="1.0"`.

**Cumple el umbral (0 citas a obsoletas).**

## PP-07 — Citas a la base de conocimiento

**Umbral literal (PP-07.md):** ≥ 95 % de hallazgos con fuente correcta y vigente, sobre una base de conocimiento de **piloto** (20-50 documentos reales). Esa base de piloto **no existe todavía** -- ese umbral a esa escala queda **[POR CONFIRMAR]**.

Lo que sí se midió, con datos reales y reproducibles (no una muestra de piloto), **ya con la corrección del hallazgo #3** (búsqueda de "referencia" aparte):

```
tests/integration/test_pp07_pp08_pp20_base_conocimiento.py::test_pp07_citas_de_una_muestra_real_son_correctas_y_vigentes PASSED
PP-07 (muestra reproducible de 12 consultas reales, no la muestra de piloto de PP-07.md): 100.0% fuente correcta+vigente

tests/integration/test_pp07_pp08_pp20_base_conocimiento.py::test_pp07_referencia_aparece_aunque_el_top_k_de_reglas_este_lleno PASSED
PP-07 (regresión): con top_k=3 (producción), la 'Referencia' para una consulta real de EST-001 es: 'Referencia: EST-001, cap. §1'
```

| Consultas | Fuente esperada | Categoría | Correcta y vigente |
| --- | --- | --- | --- |
| 7 (una por sección real de POL-001 v2.0) | POL-001 | Regla aplicada | 7/7 |
| 5 (una por sección real de EST-001) | EST-001 | Referencia | 5/5 |
| **Total** | | | **12/12 (100 %)** |

Antes de la corrección del hallazgo #3, la muestra de EST-001 daba 0/5 (la "Referencia" era siempre `None`, ver `tests/integration/test_pp07_pp08_pp20_base_conocimiento.py::test_pp07_referencia_aparece_aunque_el_top_k_de_reglas_este_lleno`, que ahora es una prueba de regresión positiva).

**Estado:** el invariante de diseño (fuente correcta + vigente, tanto "Regla aplicada" como "Referencia") se cumple al 100 % sobre la muestra real disponible; el umbral de PP-07 a escala de **piloto** (20-50 documentos reales) sigue **[POR CONFIRMAR]** hasta que exista esa base de conocimiento -- esto no cambió con la corrección, solo mejoró la fiabilidad de lo que sí se puede medir hoy.

## PP-20 — Ingesta de documentos con citas correctas (nuevo, ver `docs/04-pruebas/casos-prueba/PP-20.md`)

**Umbral:** 100 % de las citas de la muestra referencian la sección/página correcta del documento ingerido.

```
tests/integration/test_pp07_pp08_pp20_base_conocimiento.py::test_pp20_ingesta_pdf_produce_citas_con_seccion_correcta PASSED
tests/integration/test_pp07_pp08_pp20_base_conocimiento.py::test_pp20_ingesta_docx_produce_citas_con_seccion_correcta PASSED
```

| Formato | Documento real | Sección verificada | ¿Coincide? |
| --- | --- | --- | --- |
| .pdf | POL-001_Politica_Cierre_EJEMPLO.pdf | §3 (+ página) | Sí |
| .docx | EST-001_Guia_Estilo_EJEMPLO.docx | sección con marca §N | Sí |

Encadena por primera vez, con documentos reales de ambos formatos, todo el flujo `curaduria.extraccion.extraer_fragmentos` → `curaduria.indexacion.indexar_fuente` → `rag.busqueda.buscar_fragmentos` → `construir_citas`, verificando la cita resultante contra la sección/página real del fragmento extraído (antes, la ingesta y las citas se probaban por separado). Ambas pruebas usan ya los parámetros de producción (`top_k=3` por defecto) -- antes de la corrección del hallazgo #3 (búsqueda de "referencia" aparte), la del .docx necesitaba un `top_k` artificialmente ampliado para poder pasar.

**Cumple el umbral, sobre una muestra de 2 documentos (no la escala de piloto).**

## Importador de plantilla — errores sembrados (K2, RF-16)

```
tests/unit/test_curaduria_plantilla.py::test_leer_plantilla_con_errores_sembrados_en_las_cinco_hojas_a_la_vez PASSED
tests/unit/test_curaduria_api.py::test_importar_plantilla_con_errores_no_persiste_nada PASSED
```

Se sembraron **5 tipos de error distintos a la vez, uno por hoja** (antes solo existía un caso con 2 tipos en 2 hojas):

| Hoja | Tipo de error sembrado |
| --- | --- |
| Inventario de fuentes | `estado` inválido ("publicado") |
| Catálogo de cuentas | código de cuenta duplicado |
| Reglas contables | `fuente_id` de regla inexistente en el inventario |
| Glosario | `vigente_desde` con fecha inválida |
| Checklist de cierre | columna `n` no numérica |

`leer_plantilla()` reunió los 5 en una sola pasada (sin detenerse en el primero) tanto a nivel de función de dominio como del endpoint real `POST /curaduria/plantilla/importar`; en ambos casos `es_valido=False` y no se persistió ninguna fila (`FuenteConocimiento.count() == 0`, y lo mismo para cuentas/reglas/glosario/checklist a nivel de dominio).

Camino feliz (plantilla real, ya cubierto desde K2, reconfirmado): `test_leer_plantilla_real_es_valida_y_cuenta_todas_las_filas` -- 8 fuentes, 42 cuentas, 14 reglas, 16 términos de glosario, 12 actividades de checklist.

## Regresión CU-01 / CU-05

- **CU-01:** `tests/unit/test_pipeline_contable.py`, `test_api.py::test_flujo_completo_cu01_carga_y_consulta_de_estado`, `test_pp01_deteccion_contable.py` -- todos en verde. E2E real (Playwright, stack completo levantado): `flujo-analista-revisor.spec.ts` -- **1 passed**.
- **CU-05:** `tests/integration/test_cu05_pp03_pp04.py` (PP-03/PP-04, LanguageTool + Ollama reales) -- **10 passed**, recall 91.7 % (22/24), **0 % falsos positivos** (mejoró del 4.2 % de O6), los 5 documentos cumplen RNF-04. El recall bajó de 23/24 (O6) a 22/24 -- investigado a fondo (ver bug #2 arriba y `docs/04-pruebas/resultados/local-S2.md`, actualización 2026-09-30): no es una regresión de código, es la falta de `temperature=0`/`seed` fija en las llamadas al LLM, ahora corregida y confirmada estable en 3 corridas idénticas.
- Ninguna de las dos se rompió por los cambios de K1-K7 (confirmado también en K5 y K6 de este mismo bloque de trabajo).

## PP-14 (modo offline, Bloque K6) — reconfirmado

```
tests/integration/test_pp14_modo_offline.py -- 4 passed
```

Sin cambios desde K6; se reconfirma en esta corrida final junto con el resto.

## Suite completa (backend)

```
LANGUAGETOOL_HOST=127.0.0.1 LLM_BASE_URL=http://127.0.0.1:11434 .venv/Scripts/python.exe -m pytest tests/ -q
261 passed, 213 warnings in 243.03s (0:04:03)
```

Cobertura relevante a este bloque: `src/rag/busqueda.py`, `src/curaduria/*`, `src/rag/cliente_llm.py`, `src/rag/cliente_embeddings.py` -- 100 %.

## Hallazgos de este bloque

1. **Bug real corregido:** orden de desactivación/indexación al aprobar una nueva versión de una fuente -- afectaba directamente RF-16/PP-08 (ver bug #1 arriba).
2. **Bug real corregido:** sin `temperature=0`/`seed` fija, el recall de PP-03 (CU-05) no era reproducible entre corridas -- ver bug #2 arriba y la investigación completa en `docs/04-pruebas/resultados/local-S2.md`.
3. **Bug real corregido:** una fuente tipo `referencia` podía no aparecer nunca en las citas si el área tenía suficientes fuentes `regla_interna` -- ver bug #3 arriba.
4. `docs/06-operacion/instalacion.md` tenía un modelo LLM desactualizado (`qwen2.5:14b`); corregido en el Bloque K6.

## Pendiente

- PP-07 y PP-08 a **escala de piloto** (20-50 documentos reales, con representación real de fuentes `referencia`) siguen **[POR CONFIRMAR]** hasta que exista esa base de conocimiento -- lo verificado aquí es el invariante de diseño con una muestra pequeña pero real, no el umbral de piloto.
- El caso "de"/"dé" en subjuntivo (CU05-03, fila 19 de la hoja de respuestas) queda como límite conocido del modelo actual (`gpt-oss:20b`) con `temperature=0` -- no bloqueante (91.7 % ≥ 90 % de PP-03), documentado para no sorprender en una futura medición.
- `umbral_referencia` (0.5, similitud coseno) es un punto de partida razonable, no un valor medido contra datos de piloto -- candidato a afinar cuando exista una base de conocimiento real.
- Bloques K6/K7 no tocan stage (ADR-005): todo lo aquí medido es local.
