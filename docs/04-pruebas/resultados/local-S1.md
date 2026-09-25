# Resultados — Sprint 1 (CU-01 Excel contable)

**Versión:** 0.1.0
**Fecha:** 2026-09-25
**Relacionado con:** docs/03-diseno/secuencia/cu-01-excel-contable.md, docs/04-pruebas/casos-prueba/PP-01.md, PP-02.md, PP-07.md, PP-09.md, docs/04-pruebas/resultados/local-L1.md, local-L2.md

## Alcance

Implementación real de CU-01 (revisión contable de Excel): parser (`src/parsers/excel.py`), validador determinista de reglas RN-01 a RN-05 + RN-FORMULA (`src/validadores/contable/reglas.py`), ingesta y búsqueda RAG sobre la base de conocimiento (`src/rag/`), redacción de causa probable/corrección con LLM (`src/validadores/contable/explicacion.py`), salida marcada + JSON (`src/validadores/contable/salida.py`), endpoints de consulta y decisión de hallazgos (`src/api/main.py`), y el cableado del pipeline completo en el orquestador (`src/orquestador/orquestador/pipeline_contable.py`, `tareas.py`).

## Dataset sintético (CU-01)

10 archivos Excel generados por `tests/dataset/generar_cu01.py` en `tests/dataset/cu-01/`, con hoja de respuestas esperadas por archivo y una línea base de tiempos de revisión manual (`tests/dataset/cu-01/respuestas/linea-base-tiempos.csv`, solo de referencia — no válida como medición de RNF-04).

## Pruebas y cobertura

```
71 passed en ~42-44 s
Cobertura total: 93 % (mínimo exigido: 70 %)
```

| Módulo | Cobertura |
| --- | --- |
| api/esquemas.py, comun/almacenamiento.py, comun/modelos.py, comun/seguridad.py, comun/semillas.py, orquestador/pipeline_contable.py, rag/busqueda.py, validadores/contable/explicacion.py | 100 % |
| api/main.py | 92 % |
| parsers/excel.py | 91 % |
| validadores/contable/reglas.py | 99 % |
| validadores/contable/salida.py | 96 % |
| orquestador/tareas.py | 77 % (rama real de Celery/Ollama/Qdrant de `analizar_documento`, no ejercitada en unitarias — se verificó a mano, ver más abajo) |
| rag/cliente_embeddings.py, rag/cliente_llm.py | 0 % (clientes HTTP delgados; se verificaron con llamadas reales a Ollama, ver más abajo, no con mocks) |

`ruff check .` y `mypy src`: sin errores.

## PP-01 — Recall de detección (objetivo ≥ 90 %)

11 pruebas (`tests/unit/test_pp01_deteccion_contable.py`): una por cada uno de los 10 documentos del dataset (verifica que dispara exactamente los códigos de regla esperados, ni de más ni de menos) más una prueba de recall global.

**Resultado: recall 100 %, 0 falsos positivos.**

## PP-02 — Cero cifras incorrectas

RNF-03 se cumple en dos niveles:

1. **Funcional:** todo cálculo (cuadre, comparación de fechas, detección de duplicados, agrupación de monedas) lo hace `validadores/contable/reglas.py`; el LLM solo redacta texto a partir de un `HallazgoDetectado` ya calculado (`explicacion.py`).
2. **Estructural (prueba automatizada):** `tests/unit/test_validador_contable.py` incluye una prueba que inspecciona el código fuente de `reglas.py` y falla si aparecen identificadores relacionados con tipo de cambio (`tipo_de_cambio`, `tasa_cambio`, `exchange_rate`), para que ningún cambio futuro introduzca conversión de moneda calculada por el validador.

Verificado además en la explicación real generada por el LLM (ver más abajo): no inventó cifras ni fechas fuera de las provistas en el hallazgo.

## PP-07 — Citas correctas de la fuente

`tests/unit/test_explicacion_contable.py` verifica que `generar_explicacion` propaga `fuente_citada` desde el primer fragmento recuperado por RAG. Verificado además con RAG real (ver más abajo): la búsqueda para un hallazgo RN-05 (mezcla de moneda) recuperó la sección 5 de `kb/fuentes/politica-cierre-contable.md` (score 0.7555 con embeddings reales de `bge-m3`), y el LLM citó esa fuente en su explicación.

## PP-09 — Segregación de funciones

5 pruebas (`tests/unit/test_decisiones_contable.py`) sobre `POST /hallazgos/{id}/decision`:

- Un Revisor puede aceptar/rechazar el hallazgo de un documento cargado por otro usuario.
- **Quien cargó el documento no puede decidir sobre sus propios hallazgos, aunque tenga rol Administrador** (RN-07) — 403, sin crear `Decision` ni cambiar el estado del hallazgo.
- Un Analista no puede llamar al endpoint de decisión (403).
- Un `resultado` fuera de `{aceptado, rechazado, deshecho}` devuelve 422.

## Pipeline contable de extremo a extremo (con mocks de infraestructura)

`tests/unit/test_pipeline_contable.py` (3 pruebas) ejercita `ejecutar_analisis` con S3 mockeado (`moto`) y Qdrant en memoria:

- Documento con un hallazgo (cuenta inexistente): crea 1 `Hallazgo`, sube una segunda `VersionDocumento` marcada (`es_corregida=True`) con la celda coloreada y comentada, `documento.estado == "con_hallazgos"`.
- Documento limpio: 0 `Hallazgo`, no se sube versión corregida, `documento.estado == "en_revision"`.
- Sin dependencias de RAG/S3 inyectadas (tipo de revisión sin adaptador): preserva el flujo genérico de L2, sin romper `tests/unit/test_orquestador_tareas.py`.

## Verificación manual con servicios reales (no mockeada)

Con el stack local levantado (Qdrant y Postgres reales del `compose.local.yml`, Ollama **nativo** de Windows por el hallazgo de rendimiento documentado en local-L1.md):

| Verificación | Resultado |
| --- | --- |
| Ingesta RAG real (`bge-m3` vía Ollama nativo → Qdrant real), 6 fragmentos de `kb/fuentes/politica-cierre-contable.md` | 10.28 s de ingesta; 3 consultas de prueba, cada una recuperó como primer resultado la sección de la política que la responde: "mezcla quetzales/dólares sin tipo de cambio" → sección 5 (RN-05, score 0.7555); "el total no coincide entre debe y haber" → sección 1 (RN-01, score 0.6031); "fecha del mes pasado" → sección 3 (RN-03, score 0.6208). Búsquedas: 158-657 ms |
| Redacción LLM real de un hallazgo RN-05 (`llama3.2:3b`, tras cambiar de `qwen2.5:14b` por timeout) | 92.16 s; texto en español, causa probable y corrección sugerida correctas, cita `politica-cierre-contable` sección 5, sin cifras inventadas |
| Endpoint `/api/embed` de Ollama 0.34.4 | `/api/embeddings` (deprecado) devuelve 404; `/api/embed` con `input` (no `prompt`) funciona, respuesta en `embeddings[0]` |

## Tiempos de referencia por documento (no válidos para RNF-04)

Medición real del parser + validador determinista (sin LLM ni RAG) sobre los 10 documentos del dataset, solo como referencia de orden de magnitud — **no cuenta como medición de RNF-04**, que exige el pipeline completo (parser + reglas + RAG + LLM) contra hardware de stage, aún pendiente de ADR-005:

| Documento | Parser + reglas | Hallazgos |
| --- | --- | --- |
| cu01-01-limpio.xlsx | 19.2 ms | 0 |
| cu01-02-descuadre.xlsx | 14.8 ms | 1 |
| cu01-03-cuenta-inexistente.xlsx | 17.1 ms | 1 |
| cu01-04-formula-reemplazada.xlsx | 14.3 ms | 1 |
| cu01-05-fecha-fuera-periodo.xlsx | 12.8 ms | 1 |
| cu01-06-duplicado.xlsx | 14.9 ms | 2 |
| cu01-07-mezcla-moneda.xlsx | 17.0 ms | 1 |
| cu01-08-multiples-errores.xlsx | 16.7 ms | 2 |
| cu01-09-limpio-grande.xlsx (50 partidas) | 24.9 ms | 0 |
| cu01-10-multiples-errores-2.xlsx | 13.0 ms | 4 |

El costo dominante del pipeline completo es la redacción con LLM por hallazgo (~92 s con `llama3.2:3b` nativo en este equipo, ver arriba) — el parser y las reglas deterministas son órdenes de magnitud más rápidos y no son el cuello de botella.

## Comparación de modelos LLM: gpt-oss:20b vs llama3.2:3b (2026-09-25)

Medición real (sin mocks) sobre 2 documentos del dataset, con RAG real (Qdrant + `bge-m3`) y Ollama nativo, usando exactamente el mismo prompt (`construir_prompt` de `validadores/contable/explicacion.py`). Tokens/s calculado desde `eval_count`/`eval_duration` que devuelve la API de Ollama (no estimado).

| Documento | Hallazgos | Modelo | Tiempo total doc. | tok/s | Tokens generados |
| --- | --- | --- | --- | --- | --- |
| cu01-07-mezcla-moneda.xlsx | 1 (RN-05) | llama3.2:3b | 50–86 s | 5.8–9.3 | 253–353 |
| cu01-07-mezcla-moneda.xlsx | 1 (RN-05) | gpt-oss:20b | 224.6 s (3.74 min) | 3.3 | 724 |
| cu01-08-multiples-errores.xlsx | 2 (RN-01, RN-02) | llama3.2:3b | 65–69 s | 7.1–8.8 | 392–407 |
| cu01-08-multiples-errores.xlsx | 2 (RN-01, RN-02) | gpt-oss:20b | 224–238 s (3.7–4.0 min) | 3.2–3.5 | 626–742 |

(Los rangos de `llama3.2:3b` vienen de dos corridas reales independientes — hay variación normal de carga del sistema entre corridas; con `gpt-oss:20b` se reporta la corrida final, limpia.)

**Criterio de la tarea: ≤ 10 min/documento → se cumple para ambos modelos** en los 2 documentos probados (peor caso observado: 4.0 min). Extrapolando al peor caso del dataset (4 hallazgos, ver `cu01-10-multiples-errores-2.xlsx` en la tabla de arriba) a ~120 s/hallazgo con `gpt-oss:20b`, el estimado sigue por debajo de 10 min (~8 min).

**Calidad de las explicaciones (revisión manual de los textos completos):**
- `gpt-oss:20b` produce explicaciones más estructuradas (causa probable / corrección numeradas), cita la fuente entre corchetes de forma más consistente y explícita (`[politica-cierre-contable]`, a veces más de una vez por respuesta), y da pasos de corrección más concretos y accionables. No inventó cifras: reutilizó los montos exactos del hallazgo (900.00 / 850.00) sin recalcular nada, consistente con RNF-03.
- `llama3.2:3b` es 3–4x más rápido y las respuestas son correctas en sustancia, pero con más relleno conversacional innecesario ("¡Claro! A continuación...") y menos estructura.
- **Riesgo observado (no reproducible):** en una corrida exploratoria previa (prompt idéntico, misma llamada RN-01), `gpt-oss:20b` escribió una vez "50 soles" en vez de "50 quetzales/Q" — un error de terminología de moneda (Perú en vez de Guatemala), no reproducido en la corrida final documentada arriba. No es invención de cifras (el monto era correcto), pero sí un recordatorio de que ambos modelos requieren la revisión humana ya obligatoria por diseño (PP-09, rol Revisor) antes de aceptar cualquier explicación generada.

**Decisión:** se cambia `LLM_MODEL_PRINCIPAL` a `gpt-oss:20b` en `.env.local`/`.env.local.example` (antes `llama3.2:3b`), por la mejor calidad/estructura observada y porque el tiempo por documento sigue dentro del criterio de la tarea. Se sube el timeout por defecto de `rag/cliente_llm.py` de 180 s a 300 s: la llamada de 224.6 s medida arriba ya superaba el timeout anterior, lo que habría hecho fallar al worker real en producción con el modelo nuevo. `llama3.2:3b` se mantiene descargado como alternativa rápida para iteración.

**Reverificación en vivo con `gpt-oss:20b` como modelo por defecto** (stack real reconstruido, sin mocks): se repitió el flujo completo de `cu01-07-mezcla-moneda.xlsx` con `periodo_cierre=2026-01`. Resultado: **1 hallazgo (RN-05)**, sin los falsos positivos de RN-03 que aparecían antes de la corrección del período — confirma en el mismo paso que el arreglo de `periodo_cierre` (ver commit `feat(api): agrega periodo_cierre...`) funciona correctamente en el pipeline real. Texto generado en español correcto, sin inventar cifras.

Efecto secundario observado durante esta verificación: el healthcheck de `worker` (`celery inspect ping -t 5`, timeout de Docker de 10 s) marcó el contenedor como `unhealthy` varias veces mientras `gpt-oss:20b` consumía la CPU para la llamada de ~3 min — el comando de ping sí respondía ("pong"), solo tardaba más de 10 s en completarse bajo esa contención de CPU en este hardware sin GPU. El contenedor no se reinició (`restart: unless-stopped` no actúa sobre "unhealthy") y se recuperó solo al bajar la carga. No se ajustó el healthcheck en este bloque — queda anotado como algo a revisar si se vuelve recurrente en stage.

## Hallazgos de esta fase

1. **`completar_carga` (L2) no persistía la ubicación del archivo subido.** El endpoint completaba la carga multiparte en S3/MinIO pero nunca guardaba un `VersionDocumento`, así que el orquestador no tenía forma de saber qué objeto descargar. Corregido: `completar_carga` ahora crea la `VersionDocumento` inicial (`numero_version=1`, `es_corregida=False`) con la misma llave usada en la carga.
2. **`ejecutar_analisis` se mantuvo retrocompatible con L2.** El pipeline contable solo se activa cuando `tipo_revision == "contable"` **y** se inyectan todas las dependencias de infraestructura (S3, Qdrant, embeddings, LLM); sin ellas (como en las pruebas de L2 y para tipos de revisión sin adaptador todavía) se preserva el flujo genérico sin validadores. Esto evitó romper `tests/unit/test_orquestador_tareas.py`.
3. **Ollama 0.34.4 retiró `/api/embeddings`.** Confirmado en la verificación real (ver tabla arriba); `cliente_embeddings.py` usa `/api/embed` con `input` en vez de `prompt`, y lee `embeddings[0]` (plural) en vez de `embedding`.

## Pendiente

- ~~MinIO/Docker Hub sigue bloqueado~~ **Resuelto** (ver docs/04-pruebas/resultados/local-localstack.md): MinIO descontinuó toda distribución gratuita (no era un problema de credenciales); se reemplazó por LocalStack en local y se verificó el flujo `carga→S3→orquestador→pipeline CU-01` completo en vivo, sin mocks, incluyendo varios bugs reales descubiertos al correr el stack completo por primera vez.
- RNF-04 (tiempo máximo de procesamiento) sigue sin medirse contra el pipeline completo en hardware de stage — depende de ADR-005 (aún no resuelto). En este equipo, sin GPU, tanto `gpt-oss:20b` (modelo por defecto desde esta comparación) como `llama3.2:3b` quedan dentro de ≤10 min/documento; `qwen2.5:14b` excede el timeout de prueba y se descarta. La verificación E2E real de local-localstack.md midió el pipeline completo en esta máquina: ~92 s para 4 hallazgos con `llama3.2:3b`.
- Los tipos de revisión distintos de "contable" (Word, PDF, PowerPoint, imágenes) no tienen adaptador todavía; siguen el flujo genérico de L2.
