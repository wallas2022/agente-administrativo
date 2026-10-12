# Resultados — P-13 (Dashboard del Administrador), Bloque 1 (Registro de uso)

**Versión:** 0.1.0
**Fecha:** 2026-10-12
**Relacionado con:** docs/05-prompts/P-13-dashboard-administrador-consumo.md, ADR-009, docs/02-analisis/06-analisis-dashboard-administrador.md

## Alcance

Migración de la tabla `uso_llm`; `rag/cliente_llm.py` y `rag/cliente_embeddings.py` exponen las métricas que Ollama ya devuelve (tokens, duraciones) sin cambiar el contrato `Callable[[str], str]`/`Callable[[str], list[float]]` que usa todo el proyecto; cada llamada real al LLM/embeddings queda registrada con usuario, área, análisis y caso de uso -- incluidos timeouts y errores, sin frenar nunca el análisis (RNF-15).

## `comun/modelos.py` + migración

`UsoLlm`: `usuario_id`/`area_id` (FK obligatorias), `analisis_id` (FK opcional -- nulo para `embeddings_kb`, que no tiene análisis de por medio), `caso_uso`, `modelo`, `fecha_hora`, 6 columnas de métricas (todas opcionales, nunca estimadas si Ollama no las informa -- R-15), `resultado` (`ok`/`timeout`/`error`). Índices en `fecha_hora`, `usuario_id` y `caso_uso` (los tres filtros que HU-26..28 van a necesitar). Migración `0806306a1cc8` (down_revision `7a01fd7275ed`, el head de P-12), autogenerada con Alembic y **aplicada contra el Postgres local real**.

## `rag/cliente_llm.py` / `rag/cliente_embeddings.py`

`generar_texto_con_metricas`/`obtener_embedding_con_metricas` son funciones nuevas que devuelven texto/vector **y** `MetricasOllama` (tokens de entrada/salida, duración total/carga/lectura/generación, todas en milisegundos). `generar_texto`/`obtener_embedding` (las que ya usa todo el proyecto) pasan a ser envoltorios delgados que solo devuelven el texto/vector -- **sin cambiar su firma**, confirmado por las 13 pruebas ya existentes de estos dos módulos, que siguen en verde sin tocarlas.

## El hallazgo de este bloque: Depends + fakes de prueba vs. métricas reales

Dos endpoints de `api/main.py` (`mejorar_redaccion_stream`, `aprobar_fuente_endpoint`) reciben `funcion_llm`/`funcion_embedding` vía `Depends(obtener_funcion_llm)`/`Depends(obtener_funcion_embedding)` -- y las pruebas existentes (`test_api_mejorar_redaccion_stream.py`, `test_curaduria_api.py`) **sobreescriben esa inyección con una función falsa** para no golpear un Ollama real durante la suite unitaria. Envolver esas funciones ya inyectadas llamando directo a `generar_texto_con_metricas` (como sí se puede hacer en `orquestador/tareas.py`, donde no hay este problema) habría ignorado el fake de la prueba y disparado una llamada HTTP real en cada corrida de la suite.

Se resolvió con un `ContextVar` (`ULTIMAS_METRICAS_LLM`/`ULTIMAS_METRICAS_EMBEDDING` en los propios clientes): `generar_texto`/`obtener_embedding` dejan ahí sus métricas justo antes de devolver el texto/vector; quien envuelve una función **ya inyectada** (`comun.uso_llm.envolver_funcion_llm_inyectada`/`envolver_funcion_embedding_inyectada`) la llama normalmente y lee el contextvar justo después -- si es la función real, las métricas están; si es un fake de prueba que nunca pasa por `generar_texto`, el contextvar queda en `None` y la fila se registra igual, con `modelo="desconocido"`, sin romper nada. Se resetea a `None` antes de cada llamada para no arrastrar un valor de una llamada anterior.

Para `orquestador/tareas.py` (`analizar_documento`, `validar_dudosos_ortografia`), que sí controla directamente qué función real se pasa (no hay DI de FastAPI de por medio), se usan `envolver_generar_texto`/`envolver_obtener_embedding` -- construyen la función envuelta llamando a `generar_texto_con_metricas`/`obtener_embedding_con_metricas` directamente, con el modelo/kwargs exactos que ya se usaban.

## Los 4 puntos de integración

| Punto | Caso de uso | Mecanismo |
| --- | --- | --- |
| `orquestador/tareas.py::analizar_documento` | `contable` / `ortografia` (según `tipo_revision`) para el LLM; `embeddings_busqueda` para RAG | `envolver_generar_texto`/`envolver_obtener_embedding` (función real conocida) |
| `orquestador/tareas.py::validar_dudosos_ortografia` | `ortografia` (fase 2 async, CU-05) | `envolver_generar_texto` |
| `api/main.py::mejorar_redaccion_stream` (`_generador`, sesión propia `sesion_fase2`) | `redaccion` para el LLM; `embeddings_busqueda` para RAG | `envolver_funcion_llm_inyectada`/`envolver_funcion_embedding_inyectada` (función inyectada, posible fake) |
| `api/main.py::aprobar_fuente_endpoint` | `embeddings_kb` (indexación de la Base de Conocimiento, CU-08; sin `analisis_id`) | `envolver_funcion_embedding_inyectada` |

`ejecutar_analisis` y `ejecutar_validacion_dudosos_ortografia` (la lógica pura, probada con funciones falsas desde hace mucho) **no se tocaron**: el envoltorio se arma en la tarea Celery que sí conoce el usuario/área/análisis real, un nivel arriba.

## Pruebas

15 pruebas nuevas: `test_uso_llm.py` (7 -- una llamada simulada genera su fila con los valores correctos; un timeout o un error generan `resultado=timeout`/`error` y de todas formas relanzan la excepción original; `registrar_uso_llm` nunca propaga un fallo de la base), `test_cliente_llm.py`/`test_cliente_embeddings.py` (+6 -- métricas expuestas, `None` si Ollama no informa un campo, `generar_texto`/`obtener_embedding` siguen devolviendo solo texto/vector), `test_orquestador_tareas.py` (+2 -- `analizar_documento` y `validar_dudosos_ortografia` envuelven con el usuario/área/análisis correctos, verificado llamando a la función envuelta con un `httpx.post` simulado). Además, 3 pruebas existentes (`test_api_mejorar_redaccion_stream.py`, `test_curaduria_api.py` ×2 assertions) se extendieron para confirmar el registro end-to-end a través de los endpoints reales (incluida la cuenta exacta: 7 filas `embeddings_kb`, una por fragmento indexado).

## Resultado

| Ruta | Cambio | Prueba |
| --- | --- | --- |
| `comun/modelos.py`, migración `0806306a1cc8` | Tabla `uso_llm` (aplicada contra Postgres local real) | ok |
| `rag/cliente_llm.py`, `rag/cliente_embeddings.py` | `*_con_metricas`, `ContextVar` de métricas | ok -- 19 passed (13 existentes + 6 nuevas) |
| `comun/uso_llm.py` (nuevo) | `registrar_uso_llm`, 4 funciones de envoltura | ok -- 7 passed |
| `orquestador/tareas.py` | `analizar_documento`, `validar_dudosos_ortografia` instrumentados | ok -- 6 passed (4 existentes + 2 nuevas) |
| `api/main.py` | `mejorar_redaccion_stream`, `aprobar_fuente_endpoint` instrumentados | ok -- 22 passed (ambos archivos de prueba, con las nuevas aserciones) |

```
tests/unit (suite completa): 620 passed en 242.90 s (605 + 15 nuevas)
ruff check src tests / mypy: sin hallazgos
```

## Pendiente (explícitamente de otros bloques de P-13)

- Retención de `uso_llm` (P-13 §6 menciona 13 meses): no hay todavía un job de purga -- queda para el Bloque 5 o una iteración aparte, igual que RNF-12 (retención de documentos) ya tiene la suya.
- `node-exporter`/`cAdvisor`/`prometheus.yml` -- Bloque 2.
- Endpoints `GET /admin/dashboard/*` -- Bloque 3.
- Pantalla del Dashboard -- Bloque 4.

¿Continúo con el Bloque 2 (Métricas de infraestructura: `node-exporter` + `cAdvisor` + corregir `prometheus.yml`)?
