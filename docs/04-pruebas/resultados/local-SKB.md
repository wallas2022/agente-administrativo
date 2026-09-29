# Resultados — Base de conocimiento gobernada (Bloques K0-K7)

**Versión:** 0.1.0
**Fecha:** 2026-09-29
**Relacionado con:** docs/04-pruebas/casos-prueba/PP-07.md, PP-08.md, PP-14.md, PP-20.md · docs/04-pruebas/plan-pruebas-prototipo.md (v0.3) · docs/01-requerimientos/01-requerimiento-formal.md (v0.8) · docs/03-diseno/er/modelo-datos.md · docs/03-diseno/flujos/ingesta-conocimiento.md · docs/04-pruebas/resultados/local-S2.md (CU-05/RNF-04)

Cierre de pruebas del Bloque K7 sobre la base de conocimiento gobernada (RF-16, RF-17, CU-08) implementada en K0-K6: modelo de fuentes (K1), importador de plantilla (K2), ingesta de documentos (K3), búsqueda con prioridad y citas separadas (K4), pantalla del curador (K5) y modo offline (K6). Todo lo medido aquí corre contra el stack local real (Postgres, Qdrant, Ollama nativo, LanguageTool) — sin mocks salvo donde se indica explícitamente (S3 vía moto).

Comando de referencia para reproducir el backend completo:
```bash
LANGUAGETOOL_HOST=127.0.0.1 LLM_BASE_URL=http://127.0.0.1:11434 \
    .venv/Scripts/python.exe -m pytest tests/ -q
```

## Bug real encontrado y corregido en este bloque

Al escribir la prueba de PP-08 se encontró que **aprobar una segunda versión de una fuente podía dejar sus propios fragmentos recién indexados marcados como "obsoleta"**: el endpoint `POST /curaduria/fuentes/{id}/aprobar` (`src/api/main.py`) indexaba la nueva versión y *después* desactivaba los fragmentos de la fuente por `fuente_id` de negocio -- pero v1 y v2 comparten ese mismo `fuente_id` (p. ej. "POL-001"), así que la desactivación apagaba también los puntos que se acababan de indexar como vigentes. El propio test que lo cubría (`test_aprobar_una_segunda_version_obsoletea_la_primera`, Bloque K5) ya documentaba esto como limitación aceptada ("solo importa que no truene").

**Corrección:** invertir el orden -- desactivar los fragmentos de la versión anterior *antes* de indexar los de la nueva (`src/api/main.py`, `aprobar_fuente_endpoint`). Verificado con una aserción nueva que retira los puntos de v2 de Qdrant por su `referencia_vector` real y confirma `estado="vigente"` (antes fallaba con `estado="obsoleta"`).

## PP-08 — Uso solo de fuentes vigentes

**Umbral:** 0 citas a versiones obsoletas.

```
tests/integration/test_pp07_pp08_pp20_base_conocimiento.py::test_pp08_ninguna_cita_referencia_la_version_obsoleta PASSED
```

Ingesta real de las dos versiones de la misma política (`POL-000_..._OBSOLETA_EJEMPLO.pdf` como v1.0, obsoletada; `POL-001_..._EJEMPLO.pdf` como v2.0, vigente) vía el ciclo de vida real de CU-08 (`curaduria.fuentes.aprobar_fuente` + `curaduria.indexacion.indexar_fuente`, ya con el orden corregido). Se consultó con las 7 secciones reales de v2.0 (contenido casi idéntico al de v1.0, la edición anterior de la misma política -- el caso más exigente posible) y **0 de 7** citas referenciaron `version="1.0"`.

**Cumple el umbral (0 citas a obsoletas).**

## PP-07 — Citas a la base de conocimiento

**Umbral literal (PP-07.md):** ≥ 95 % de hallazgos con fuente correcta y vigente, sobre una base de conocimiento de **piloto** (20-50 documentos reales). Esa base de piloto **no existe todavía** -- ese umbral a esa escala queda **[POR CONFIRMAR]**.

Lo que sí se midió, con datos reales y reproducibles (no una muestra de piloto):

```
tests/integration/test_pp07_pp08_pp20_base_conocimiento.py::test_pp07_citas_de_una_muestra_real_son_correctas_y_vigentes PASSED
PP-07 ('Regla aplicada', muestra reproducible de 7 consultas reales, no la muestra de piloto de PP-07.md): 100.0% fuente correcta+vigente
```

| Consultas | Fuente esperada | Correcta y vigente |
| --- | --- | --- |
| 7 (una por sección real de POL-001 v2.0) | POL-001 (regla_interna, vigente) | 7/7 (100 %) |

**Hallazgo (no es una falla de umbral, se deja documentado a propósito):**

```
tests/integration/test_pp07_pp08_pp20_base_conocimiento.py::test_pp07_hallazgo_referencia_puede_quedar_fuera_del_top_k_por_prioridad PASSED
PP-07 (hallazgo, no umbral): con top_k=3 (producción), la 'Referencia' para una consulta real de EST-001 es: None
```

`rag.busqueda.buscar_fragmentos` ordena primero por prioridad y solo después por similitud (diseño intencional del Bloque K4, ya probado en `tests/unit/test_rag.py`). Consecuencia real: en un área donde una fuente `regla_interna` tiene al menos `top_k` fragmentos vigentes, una fuente `referencia` puede no aparecer **nunca** como cita, incluso siendo la más relevante semánticamente para la consulta -- porque el filtro de prioridad se aplica sobre los candidatos ya truncados por similitud, antes de que `construir_citas` los vea. No se cambió el comportamiento (es una decisión de negocio de K4, no un defecto); se deja para una futura revisión de RF-12 si se decide que "Referencia" merece su propia búsqueda independiente de "Regla aplicada".

**Estado:** el invariante de diseño (fuente correcta + vigente cuando es de la máxima prioridad) se cumple al 100 % sobre la muestra real disponible; el umbral de PP-07 a escala de piloto (20-50 documentos, con documentos `referencia` representados proporcionalmente) queda **[POR CONFIRMAR]** hasta que exista esa base de conocimiento.

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

Encadena por primera vez, con documentos reales de ambos formatos, todo el flujo `curaduria.extraccion.extraer_fragmentos` → `curaduria.indexacion.indexar_fuente` → `rag.busqueda.buscar_fragmentos` → `construir_citas`, verificando la cita resultante contra la sección/página real del fragmento extraído (antes, la ingesta y las citas se probaban por separado; ver hallazgo de PP-07 sobre por qué la prueba del .docx usa un `top_k` ampliado).

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
- **CU-05:** `tests/integration/test_cu05_pp03_pp04.py` (PP-03/PP-04, LanguageTool + Ollama reales) -- **10 passed**, recall 91.7 % (22/24), falsos positivos 0.0 %, los 5 documentos del dataset cumplen RNF-04 (≤ 5 min/documento, SRS v0.8; el PDF es el más ajustado con 80.6s de 300s límite). Sin cambios respecto a lo ya registrado en `docs/04-pruebas/resultados/local-S2.md`.
- Ninguna de las dos se rompió por los cambios de K1-K7 (confirmado también en K5 y K6 de este mismo bloque de trabajo).

## PP-14 (modo offline, Bloque K6) — reconfirmado

```
tests/integration/test_pp14_modo_offline.py -- 4 passed
```

Sin cambios desde K6; se reconfirma en esta corrida final junto con el resto.

## Suite completa (backend)

```
LANGUAGETOOL_HOST=127.0.0.1 LLM_BASE_URL=http://127.0.0.1:11434 .venv/Scripts/python.exe -m pytest tests/ -q
257 passed, 213 warnings in 231.80s (0:03:51)
```

Cobertura relevante a este bloque: `src/rag/busqueda.py`, `src/curaduria/*`, `src/rag/cliente_llm.py`, `src/rag/cliente_embeddings.py` -- 100 %.

## Hallazgos de este bloque

1. **Bug real corregido:** orden de desactivación/indexación al aprobar una nueva versión de una fuente (ver sección dedicada arriba) -- afectaba directamente RF-16/PP-08.
2. **Hallazgo de diseño documentado, no corregido:** una fuente tipo `referencia` puede quedar permanentemente fuera de toda cita en un área con suficientes fuentes `regla_interna`, por el orden prioridad-antes-que-similitud de K4 (ver sección PP-07). Candidato para una futura revisión de RF-12.
3. `docs/06-operacion/instalacion.md` tenía un modelo LLM desactualizado (`qwen2.5:14b`); corregido en el Bloque K6.

## Pendiente

- PP-07 y PP-08 a **escala de piloto** (20-50 documentos reales, con representación real de fuentes `referencia`) siguen **[POR CONFIRMAR]** hasta que exista esa base de conocimiento -- lo verificado aquí es el invariante de diseño con una muestra pequeña pero real, no el umbral de piloto.
- El hallazgo de diseño (punto 2 arriba) no tiene solución propuesta todavía; queda para una futura revisión de RF-12/K4 si se decide que importa (p. ej. buscar "Referencia" con su propio `top_k` independiente de "Regla aplicada").
- Bloques K6/K7 no tocan stage (ADR-005): todo lo aquí medido es local.
