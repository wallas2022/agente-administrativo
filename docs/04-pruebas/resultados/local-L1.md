# Resultados — L1 Infra local

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** docs/03-diseno/despliegue/estrategia-ambientes.md, infra/compose.local.yml, docs/03-diseno/adr/ADR-001-motor-llm-cpu.md

Ejecutado en la máquina real de desarrollo (no es el "128 GB RAM" que documenta el SRS v0.6 — ver discrepancia registrada en el bloque L0). Specs reales: Intel Core Ultra 7 255H (16 núcleos), **30.9 GB RAM total**, SSD, sin GPU dedicada. Docker Desktop / WSL2 (`.wslconfig` sin `memory=` explícito) asigna por defecto ~15 GB a la VM de Docker, compartidos con otros proyectos que ya corrían en esta máquina.

## 1. Estado de los servicios

| Servicio | Estado | Notas |
| --- | --- | --- |
| proxy (Traefik) | healthy | Requirió agregar `--ping=true` al comando (faltaba en el esqueleto de F1); el provider de Docker no logra listar contenedores (ver hallazgo 3) |
| redis | healthy | — |
| ollama | healthy | Ver §2 y §3 (rendimiento) |
| qdrant | healthy | Requirió cambiar el healthcheck de `curl` a `bash`+`/dev/tcp` (la imagen oficial no trae curl/wget) |
| postgres | healthy | — |
| languagetool | healthy | Confirmado: responde con la lista de idiomas, incluye `es`/`es-ES` |
| worker (Celery) | healthy → **unhealthy** tras la prueba de LLM | Requirió corregir `src/orquestador/orquestador/__init__.py`: el broker/backend de Celery estaba en `None` (F1), lo que hacía que intentara conectar a RabbitMQ en `127.0.0.1:5672` en vez de a Redis. Corregido para usar `REDIS_HOST`/`REDIS_PORT`/`REDIS_PASSWORD`. Volvió a `unhealthy` mientras `ollama` saturaba la CPU del host (ver §3) — a reverificar. |
| orquestador | **en bucle de reinicio** (esperado) | `src/orquestador/orquestador/__main__.py` solo imprime un mensaje y termina (F1, sin lógica de negocio); con `restart: unless-stopped` esto genera un bucle de reinicio constante. Es responsabilidad de **L2** darle un proceso de larga duración real. No se considera un defecto de L1. |
| api | **no arrancó** | Depende de `minio` (`condition: service_healthy`); ver hallazgo 1. |
| minio | **no arrancó** | Ver hallazgo 1. |

## 2. Hallazgos de infraestructura (corregidos en este bloque)

1. **`minio/minio` ya no es descargable sin autenticación.** `docker pull minio/minio:...` devuelve `pull access denied ... may require 'docker login'`; el repositorio `minio/minio` en Docker Hub responde 404 en su API pública, y `quay.io/minio/minio` exige autenticación incluso para `latest`. Esto es un cambio de distribución de MinIO posterior a cuando se fijó ese tag, no un error de configuración. **Pendiente de decisión** (ver sección "Pendiente" abajo): no se sustituyó por otra imagen sin tu confirmación.
2. **`red_interna: internal: true` bloqueaba `ollama pull` en local.** La red interna (pensada para RNF-01 en stage: sin salida a internet) estaba definida una sola vez en `compose.yml` base y se heredaba también en local, donde SÍ se necesita internet para descargar modelos/dependencias. Corregido: `compose.local.yml` ahora declara `red_interna: internal: false`; `compose.stage.yml` no la toca y sigue `internal: true`.
3. **Healthcheck de `qdrant` fallaba: la imagen no trae `curl` ni `wget`.** Cambiado a `bash -c 'exec 3<>/dev/tcp/...'` (confirmado que `bash` sí está presente).
4. **Healthcheck de `proxy` (Traefik) fallaba: faltaba `--ping=true`.** Sin ese flag, el endpoint `/ping` en el puerto 8080 no existe y `traefik healthcheck --ping` siempre falla. Agregado al `command:`.
5. **Celery (`worker`) intentaba conectarse a RabbitMQ, no a Redis.** `src/orquestador/orquestador/__init__.py` creaba `Celery("orquestador", broker=None, backend=None)`, que cae en el valor por defecto de Celery (`amqp://guest@127.0.0.1:5672`), no en "sin configurar". Corregido para construir la URL de Redis desde las variables de entorno del propio stack.
6. **Conflicto de puertos con otros proyectos Docker de esta máquina.** `443` (nginx de un stack de Greenbone), `5432` (`ocr_postgres`) y `9000-9001` (`ocr_minio`) ya estaban en uso. `compose.local.yml` ahora publica `8443`, `5433` y `9010-9011` en su lugar.
7. **El reenvío de puertos de Docker Desktop a `127.0.0.1` estaba roto para *todos* los contenedores del sistema** (incluidos los de otros proyectos, no solo los de este) justo después de iniciar el demonio. Se autocorrigió al recrear los contenedores propios; no se tocó `.wslconfig` ni el firewall de Windows (afectaría a tus otros proyectos) — si vuelve a ocurrir, probablemente se resuelva reiniciando Docker Desktop.

## 3. Prueba de humo — LLM (hallazgo crítico de rendimiento)

**Modelo usado:** `qwen2.5:7b-instruct` (4.7 GB), **no** `gpt-oss:20b` como pedía la tarea — con 30.9 GB de RAM real (no 128 GB) y ~15 GB asignados a Docker Desktop, `gpt-oss:20b` no es viable en esta máquina tal como está configurada hoy. `LLM_MODEL_PRINCIPAL` en `.env.local.example` se actualizó para reflejar esto.

**Prompt de prueba** (español): *"Eres un asistente que ayuda a revisar documentos administrativos. Explica en dos oraciones, en español, qué es un descuadre contable."*

**Resultado:** el modelo respondió correctamente en español (2 oraciones, coherentes, sobre descuadre contable) — **pero el rendimiento es inviable**:

| Métrica | Valor medido |
| --- | --- |
| Carga del modelo | 1 min 19 s |
| Prompt eval | 65 tokens en 25.9 s → **2.51 tokens/s** |
| Generación (eval) | 80 tokens en **22 min 55 s** → **0.06 tokens/s** |
| Duración total | 24 min 41 s |
| RAM vista por ollama | 6.0 GiB total / 5.9 GiB libre (límite del contenedor en ese momento) |

**Diagnóstico:** el contenedor `ollama` tenía `cpus: "4.00"` en `infra/compose.local.yml`, pero el motor detectó `n_threads = 16` (todos los núcleos lógicos del host) y hoy asigna 16 hilos de cómputo contra una cuota de solo 4 núcleos — contención de CPU severa (probable causa del salto de 2.51 a 0.06 tokens/s entre el procesamiento del prompt, paralelizable, y la generación, secuencial y muy sensible a esta contención). También el límite de memoria (6 GiB) dejaba menos de 1.5 GB de margen sobre el tamaño real del modelo cargado (~4.8 GiB entre pesos, KV cache y buffers), lo que pudo agravar el problema.

**Corrección aplicada (sin volver a medir todavía):** subí `cpus` a `8.00` y `memory` a `10G` para `ollama` en `compose.local.yml`. **No repetí la prueba de 20+ minutos con este cambio** porque cada intento cuesta esa misma cantidad de tiempo y quise reportar antes de gastar otro; ver "Pendiente" para la decisión de cómo seguir.

## 4. Verificaciones adicionales

- **LanguageTool responde:** confirmado en el propio healthcheck (`GET /v2/languages` devuelve la lista completa, incluye español).
- **Qdrant accesible solo en 127.0.0.1:** confirmado — `docker port`/`HostConfig.PortBindings` y una petición HTTP real desde el host (`http://127.0.0.1:6333/healthz` → `200 healthz check passed`) funcionan; no hay bind a `0.0.0.0`.
- **Postgres accesible solo en 127.0.0.1:** confirmado — `Test-NetConnection 127.0.0.1:5433` exitoso; no hay bind a `0.0.0.0`.

## 5. Herramientas (bloque L0, para referencia)

git 2.53.0 · Docker 29.8.0 (CLI) + demonio iniciado manualmente · Docker Compose v5.5.1 · uv 0.12.18 (instalado vía winget en este bloque) · Python 3.12 aún no instalado (pendiente para L2, vía `uv python install 3.12`).

## Pendiente (requiere tu decisión)

1. **MinIO no se puede descargar.** Opciones: (a) usar `docker login` con una cuenta que sí tenga acceso, (b) buscar otra imagen/registro S3-compatible (p. ej. una versión propia compilada, o un mirror interno), (c) posponer el almacenamiento de objetos real a una fase posterior y mockear `api`↔MinIO en L2. **`api` y el propio `minio` siguen sin arrancar hasta que se decida esto.**
2. **Rendimiento del LLM en esta máquina.** Con el ajuste de CPU/memoria ya aplicado pero sin re-medir: ¿repito la prueba ahora (~20+ min más) para confirmar si el fix funcionó, o seguimos con L2 (que no depende de esto) y dejamos el benchmark de rendimiento para más adelante? Si el problema persiste incluso con más CPU/RAM, `gpt-oss:20b`/modelos de 20B+ quedarían descartados para desarrollo local en esta máquina tal cual está hoy (sería necesario revisar si hay throttling térmico, el modo de energía de Windows, o si WSL2 en modo *mirrored* introduce overhead adicional).
