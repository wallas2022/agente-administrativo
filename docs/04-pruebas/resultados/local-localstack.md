# Resultados — Reemplazo de MinIO por LocalStack y verificación E2E real (CU-01)

**Versión:** 0.1.0
**Fecha:** 2026-09-25
**Relacionado con:** docs/04-pruebas/resultados/local-L1.md, local-L2.md, local-S1.md, docs/03-diseno/c4/02-contenedores.md

## Motivo del cambio

MinIO descontinuó toda distribución gratuita de su edición comunitaria:

| Vía intentada | Resultado |
| --- | --- |
| `docker pull minio/minio:...` (cualquier tag) | `pull access denied` — el repositorio `minio/minio` ya no existe en Docker Hub (`GET /v2/repositories/minio/minio/` → `404 object not found`) |
| `docker pull bitnami/minio:latest` (alternativa) | Repositorio activo pero sin ningún tag público (`tags/` devuelve `count: 0`) |
| `quay.io/minio/minio` | Exige autenticación incluso para leer metadatos públicos |
| Binario nativo de Windows (`dl.min.io/server/minio/release/windows-amd64/minio.exe`, incluido vía `winget install MinIO.Server`) | `410 Gone`: *"The open-source MinIO Server... are archived and no longer maintained... no longer served from this site"* |

Ninguna de las cuatro vías depende de un token de Docker Hub — no es un problema de credenciales. Se reemplazó por **LocalStack** (solo el servicio S3), que expone la misma API S3 que ya consumía `comun/almacenamiento.py` vía boto3, sin cambios de lógica de negocio. Verificado como imagen pública activa (`localstack/localstack:4.9.1`, 568M+ pulls).

El backend definitivo de almacenamiento de objetos para **stage** queda pendiente de una decisión de arquitectura (afecta SRS/ADR, fuera del alcance de este bloque de infra local); `infra/compose.stage.yml` sigue referenciando MinIO sin tocar.

## Cambios de infraestructura

- `infra/compose.yml`: servicio `minio` → `localstack` (imagen `localstack/localstack:4.9.1`, `SERVICES=s3`), healthcheck vía `/_localstack/health`; `depends_on` de `api` y `langfuse` actualizado.
- `infra/compose.local.yml`: puerto publicado `127.0.0.1:9010` → `4566` (antes `9000`); volumen `localstack_data`.
- `.env.local` / `.env.local.example`: `MINIO_ENDPOINT=localstack:4566` (las variables mantienen el prefijo `MINIO_` a propósito, para no dispersar el cambio por todo el código/documentación mientras no haya una decisión de arquitectura definitiva).
- `src/comun/almacenamiento.py`: `addressing_style: path` explícito en la config de boto3 (necesario contra un endpoint custom); default de `MINIO_ENDPOINT` actualizado.
- `infra/scripts/levantar-local.sh`: lista de servicios core actualizada.

## Bugs reales descubiertos al levantar el stack completo por primera vez

Esta es la primera vez que el contenedor `api` y el pipeline CU-01 corrieron con **todos** los servicios reales (sin mocks). Salieron a la luz varios bugs que las pruebas unitarias, por diseño, no podían atrapar:

1. **`celery`/`redis` faltaban en `comun/requirements.txt`.** `comun/cola.py` los importa, pero solo estaban declarados en `orquestador/requirements.txt` — el contenedor `api` no arrancaba (`ModuleNotFoundError: No module named 'celery'`). Movidos a `comun/requirements.txt` (compartido).
2. **`orquestador/Dockerfile` no copiaba `parsers/`, `rag/`, `validadores/` ni `kb/`.** El worker real (misma imagen que `orquestador`) no tenía el código del pipeline CU-01 ni la base de conocimiento. Se agregó su instalación/copiado, y `kb/` se incorpora vía `build.additional_contexts` (vive en la raíz del repo, fuera del build context `../src`).
3. **`pipeline_contable.RUTA_CATALOGO_POR_DEFECTO` usaba `Path(__file__).resolve().parents[3]`.** Ese índice fijo solo era correcto en el layout anidado local (`src/orquestador/orquestador/`); dentro del contenedor, el paquete queda un nivel más superficial (`/app/orquestador/`), y `parents[3]` no existía (`IndexError`). Reemplazado por una búsqueda hacia arriba de un directorio `kb/`, válida en ambos layouts.
4. **Los usuarios locales de prueba (RF-01) nunca se sembraban en la base de datos real.** `sembrar_datos_de_prueba` solo se invocaba desde las pruebas unitarias (SQLite en memoria) — el `login` funcionaba (usa el registro en memoria de `comun/seguridad.py`), pero cualquier endpoint que consultara `Usuario` en Postgres devolvía 401 "Usuario no encontrado". Se agregó un hook de `lifespan` en `api/main.py` que siembra al iniciar, solo cuando `APP_ENV=local` (nunca en pruebas ni en stage).
5. **El bucket `documentos` no existía.** Nada lo creaba fuera de las pruebas (`moto`). Mismo hook de `lifespan`: `almacenamiento.asegurar_bucket(...)`, también solo en `APP_ENV=local`.
6. **`tareas.py` construía el cliente de Qdrant desde una variable `QDRANT_URL` que no existe en ningún `.env`** (la convención real del proyecto es `QDRANT_HOST`/`QDRANT_PORT`, igual que Postgres) — el análisis real siempre caía al flujo genérico sin validadores. Corregido para construir la URL desde `QDRANT_HOST`/`QDRANT_PORT`.
7. **La colección de Qdrant estaba hardcodeada (`"kb-contable"`)** en vez de usar `QDRANT_COLECCION` (la variable ya existente en `.env.local`). Se agregó el parámetro `coleccion_rag` de extremo a extremo (`tareas.py` → `pipeline_contable.py`), con el valor hardcodeado como *fallback* cuando no se pasa explícitamente (usado por las pruebas unitarias).
8. **`hallazgo.moneda` era `VARCHAR(3)`.** RN-05 guarda la combinación de monedas mezcladas (p. ej. `"Q/USD"`, 5 caracteres), no un solo código ISO 4217 — la inserción real fallaba (`StringDataRightTruncation`). Ampliado a `VARCHAR(10)` (migración `ab2dd1e9f229`).
9. **El contenedor `qdrant`, corriendo desde antes de esta sesión, perdió su alias DNS de servicio** (`docker network inspect` mostraba `infra-qdrant-1` pero no `qdrant`) — mismo tipo de flakiness ya documentado en local-L1.md sobre el port-forwarding de Docker Desktop. Se resolvió recreando el contenedor (`--force-recreate`).

Ninguno de estos bugs era detectable con `moto`/SQLite en memoria porque todos dependen de comportamiento real de red/DNS entre contenedores, de layout de archivos dentro de la imagen, o de construir sesiones/clientes fuera del mecanismo de `dependency_overrides` que usan las pruebas.

## Verificación end-to-end real (sin mocks)

Con los 10 servicios core healthy (`proxy`, `api`, `orquestador`, `worker`, `redis`, `ollama`, `qdrant`, `postgres`, `localstack`, `languagetool`), flujo completo contra la API viva:

1. `POST /auth/login` (usuario `analista@local`, sembrado real en Postgres).
2. `POST /documentos/iniciar` + `PUT /documentos/{id}/partes/1` + `POST /documentos/{id}/completar` con `tests/dataset/cu-01/cu01-07-mezcla-moneda.xlsx` (carga real a LocalStack S3, encolado real en Redis/Celery).
3. El `worker` real consumió la tarea y ejecutó el pipeline completo: parser → reglas → búsqueda RAG en Qdrant real → redacción con Ollama nativo (`llama3.2:3b`) → persistencia de `Hallazgo` en Postgres real.
4. `GET /analisis/{id}` y `GET /analisis/{id}/hallazgos` confirmaron el resultado.

**Resultado:** `documento.estado == "con_hallazgos"`, 4 hallazgos persistidos (RN-05 mezcla de moneda + RN-03 fecha fuera de período ×3), cada uno con explicación en español generada por el LLM real, sin cifras inventadas. Tiempo total ~92 s (dominado por las 4 llamadas al LLM, consistente con la medición de local-S1.md).

**Nota de diseño encontrada, no corregida en este bloque:** `analisis.fecha_inicio` (usada como período de referencia para RN-03) se fija a "ahora" al crear el análisis (`completar_carga` en `api/main.py`), no al período contable que el usuario quiere cerrar. Por eso, al correr la prueba en 2026-09-25 contra un documento de enero 2026, RN-03 se disparó para casi todas las partidas — comportamiento correcto del código dado el diseño actual, pero indica que falta un campo explícito de "período a revisar" en la creación del análisis (no estaba en el alcance de Sprint 1). Pendiente para un sprint futuro.

## Pruebas y calidad

`ruff check .` y `mypy src`: sin errores. Suite unitaria completa (71 pruebas) sigue en verde tras todos los cambios — ningún cambio de este bloque requirió modificar una prueba existente, salvo los defaults ya cubiertos por inyección de dependencias.

## Pendiente

- Backend de almacenamiento de objetos definitivo para stage: decisión de arquitectura pendiente (afecta SRS/ADR). `infra/compose.stage.yml` y la documentación de respaldo (`infra/proxmox/vm-spec.md`, `infra/scripts/README.md`) siguen mencionando MinIO — no se tocaron en este bloque.
- Campo explícito de "período a revisar" en la creación del análisis (ver nota de diseño arriba).
- Las variables de entorno siguen con el prefijo `MINIO_` por conveniencia; renombrarlas (p. ej. a `ALMACENAMIENTO_S3_*`) es un cambio cosmético de bajo valor mientras no haya una decisión de backend definitiva.
