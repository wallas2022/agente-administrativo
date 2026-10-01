# Resultados — CU-02 "Mejorar redacción", Bloque 1 (Entrada y motor)

**Versión:** 0.1.0
**Fecha:** 2026-10-01
**Relacionado con:** docs/02-analisis/02-analisis-cu02-redaccion-amigable.md, docs/03-diseno/secuencia/cu-02-redaccion.md, docs/01-requerimientos/01-requerimiento-formal.md (RF-07, RF-12, RNF-03)

## Alcance

Motor de punta a punta de CU-02: pantalla de entrada (pestañas Pegar texto / Subir archivo, selects de tipo de documento y acción), fase 1 determinista (reglas RD-01 a RD-04 contra EST-001, en el worker) y fase 2 (LLM por párrafo con streaming SSE + guardia de integridad RNF-03, en la API). No incluye todavía la pantalla de "Resultado" (Bloque 2, que es quien realmente abre la conexión SSE desde el navegador) ni el conversor de salida (Bloque 3).

## Backend

| Ruta | Cambio | Prueba | Tiempo |
| --- | --- | --- | --- |
| `src/validadores/redaccion/reglas.py` | Reglas deterministas RD-01 a RD-04 (secciones de Procedimiento, formato de montos/fechas, siglas sin definir) contra EST-001 | `tests/unit/test_redaccion_reglas.py` (12 casos) | 3.79 s (conjunto) |
| `src/validadores/redaccion/guardia.py` | Guardia RNF-03: descarta la sugerencia del LLM si cambian cifras, fechas o nombres propios respecto al original | `tests/unit/test_redaccion_guardia.py` (6 casos) | — |
| `src/validadores/redaccion/mejora.py` | Fase 2 por párrafo: prompt por acción (Corregir/Aclarar/Formalizar), cita EST-001 vía RAG si hay fuente vigente, aplica la guardia | `tests/unit/test_redaccion_mejora.py` (6 casos) | — |
| `src/validadores/redaccion/extraccion.py` (nuevo) | Extracción de párrafos (PDF/Word/texto) compartida entre worker y API — ver nota de diseño abajo | — | — |
| `src/orquestador/orquestador/pipeline_redaccion.py` | Fase 1 (worker): extrae párrafos, corre reglas deterministas, persiste hallazgos | `tests/unit/test_pipeline_redaccion.py` (8 casos) | — |
| `src/api/main.py` | Endpoint `GET /analisis/{id}/mejorar-stream` (fase 2, streaming SSE): re-descarga el original, corre `mejorar_parrafo` por párrafo, persiste `Hallazgo` (`pendiente` o `sin_cambio` si la guardia descarta), emite eventos SSE, actualiza `documento.estado` | `tests/unit/test_api_mejorar_redaccion_stream.py` (4 casos, nuevo) | — |
| `src/api/esquemas.py`, `src/comun/modelos.py`, migración `c3f7a1d9e824` | `tipo_documento`/`accion` en `SolicitudCompletarCarga`/`Analisis` | upgrade/downgrade/upgrade contra Postgres real | — |
| `src/api/Dockerfile` | Agrega `COPY validadores ./validadores` — faltaba desde antes de este bloque; sin este cambio la imagen de la API no arrancaba (`ModuleNotFoundError: validadores`) | build Docker real + smoke test (`/health`, `/openapi.json`) | ver abajo |

```
tests/unit (suite completa): 284 passed in 47.21s
ruff check src tests: sin hallazgos
mypy src: sin hallazgos (65 archivos)
```

### Nota de diseño: por qué `extraccion.py` es un módulo nuevo

`orquestador.pipeline_redaccion.extraer_parrafos` (fase 1) no podía importarse directamente desde `api/main.py` para la fase 2: el paquete `orquestador` registra tareas de Celery al importarse (`orquestador/__init__.py` hace `from . import tareas`), algo que la API no debe arrastrar. Se extrajo la función pura a `validadores/redaccion/extraccion.py`, compartida por ambos sin acoplar la API al orquestador. De paso se encontró que `api/Dockerfile` tampoco copiaba el paquete `validadores` (ya lo necesitaba `mejora.py` desde antes de este bloque) — corregido en el mismo cambio.

### Verificación de imágenes Docker (build real, sin mocks)

```
docker build -f api/Dockerfile .            -> build OK
docker run ... (API_SECRET_KEY=...)         -> /health 200, /openapi.json incluye
                                                /analisis/{id}/mejorar-stream
docker build -f orquestador/Dockerfile \
  --build-context kb=../kb .                -> build OK
docker run ... python -c "import orquestador.pipeline_redaccion; \
  from orquestador.tareas import ejecutar_analisis"  -> import OK
```

## Frontend

| Ruta | Cambio | Prueba | Tiempo |
| --- | --- | --- | --- |
| `src/ui/src/paginas/NuevoAnalisis.tsx` | Habilita "redaccion" en `TIPOS_REVISION`; agrega extensiones válidas (.docx/.pdf); generaliza el toggle "texto pegado/archivo" (antes solo `=== "ortografia"`) a un `Set` con ambos tipos; agrega selects "Tipo de documento" y "Acción" con sus defaults | — | — |
| `src/ui/src/subida/subirDocumento.ts`, `dependenciasReales.ts` | Propagan `tipoDocumento`/`accion` hasta el body de `POST /documentos/{id}/completar` | `subirDocumento.test.ts` (10 casos, 1 nuevo para CU-02) | — |
| `src/ui/src/api/esquema.ts` | Regenerado (`openapi-typescript` contra la API real corrida en local sin Docker) — agrega `tipo_documento`/`accion` y el path `/analisis/{id}/mejorar-stream` | diff: solo adiciones (63 líneas) | — |

```
npx vitest run: 40 passed in 11.95s (7 archivos)
npx tsc --noEmit: sin errores
npm run lint (oxlint): sin hallazgos nuevos (2 warnings preexistentes, no relacionados)
```

## Hallazgos de este bloque

1. **Bug de despliegue preexistente encontrado y corregido**: `api/Dockerfile` no copiaba `validadores`, paquete que la API ya necesitaba desde que se escribió `validadores/redaccion/mejora.py` en este mismo trabajo (antes de que se verificara con un build real). Sin este bloque, el primer `docker compose up` con estos cambios habría fallado al arrancar la API.
2. **Gotcha de FastAPI con `StreamingResponse`**: una dependencia `Depends(obtener_sesion)` (con `yield`) se cierra antes de que arranque el envío del cuerpo de la respuesta — no sirve para persistir datos dentro del generador que produce el stream. Se resolvió con una dependencia nueva, `obtener_fabrica_sesion_stream`, que el generador usa para abrir y cerrar su propia sesión.
3. **Límite de columna**: `Hallazgo.estado` es `String(20)`; la etiqueta completa "sin cambio por seguridad" (24 caracteres) no entra. Se usa el código corto `"sin_cambio"` y el motivo completo queda en `descripcion` — evita una migración solo para esto.

## Pendiente (antes de considerar el Bloque 1 completamente demostrable en vivo)

- **Verificación end-to-end contra el stack local completo** (`docker compose up`, con Postgres/Qdrant/MinIO/Ollama reales): este bloque verificó los builds de imagen y las pruebas unitarias/contrato (`openapi.json`), pero no una corrida real subiendo un documento y viendo los hallazgos de redacción aparecer en pantalla.
- **Curar una fuente EST-001 "vigente" real** (pantalla del curador, Bloque K5) para que las citas "Regla aplicada: EST-001 §N" aparezcan en la fase 2 — hoy solo existe el ejemplo en `kb/plantillas/ejemplos/EST-001_Guia_Estilo_EJEMPLO.docx`, usado en pruebas pero nunca indexado como vigente.
- La pantalla de "Resultado" (Bloque 2) es la que realmente abre la conexión SSE desde el navegador — hasta que exista, el endpoint `/analisis/{id}/mejorar-stream` solo está verificado por pruebas de API, no manualmente desde la UI.
