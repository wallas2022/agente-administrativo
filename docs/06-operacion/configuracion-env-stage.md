# Configuración de `.env.stage`

**Versión:** 1.0 · **Fecha:** 2026-10-06 · **Relacionado con:** `.env.stage.example` (v2.0), `infra/compose.yml`, `infra/compose.stage.yml`, `docs/06-operacion/traslado-stage-paso-a-paso.md`, `docs/06-operacion/instalacion-modelos-ollama-stage.md`, RNF-01, RNF-02, ADR-006

> Plantilla construida leyendo el repositorio (commit local al 2026-10-06): variables que el código lee con `os.environ`, `compose.yml`/`compose.stage.yml` y `.env.local.example`. El `.env.stage.example` v1 estaba desactualizado (faltaban 5 variables y tenía 2 valores que fallan).

## 1. Dónde va y cómo se usa

```mermaid
flowchart LR
    T[.env.stage.example<br/>en Git] -->|cp + generar secretos| E[/opt/agente/app/.env.stage<br/>chmod 600 · fuera de Git/]
    E -->|--env-file ../.env.stage<br/>interpolación ${VAR}| C[infra/compose.yml<br/>+ compose.stage.yml]
    E -->|env_file: ../.env.stage| K[Contenedores<br/>api · orquestador · worker · ollama · postgres ...]
```

```bash
srv$ cd /opt/agente/app
srv$ cp .env.stage.example .env.stage && chmod 600 .env.stage
srv$ python3 - <<'EOF'
import secrets, re, pathlib
p = pathlib.Path(".env.stage"); s = p.read_text()
s = re.sub(r"<GENERAR-HEX32>", lambda _: secrets.token_hex(32), s)
s = re.sub(r"<GENERAR-B64>", lambda _: secrets.token_urlsafe(24).replace("-", "x").replace("_", "y"), s)
p.write_text(s); print("Secretos generados")
EOF
srv$ nano .env.stage                     # completar los [POR CONFIRMAR]
srv$ grep -n -E "GENERAR|POR CONFIRMAR" .env.stage   # debe quedar vacío
srv$ cd infra
srv$ docker compose --env-file ../.env.stage -f compose.yml -f compose.stage.yml config > /dev/null && echo OK
```
Cada contraseña es distinta (el script genera una por marcador). Guardar copia del `.env.stage` en el gestor de secretos del área, no en correo ni chat.

## 2. Variables

| Grupo | Variable | Valor stage | ¿La lee el código? | Nota |
| --- | --- | --- | --- | --- |
| General | `APP_ENV` | `stage` | Sí (`api/main.py`) | ≠ `local` → no siembra usuarios ni crea buckets (§4) |
| API | `API_SECRET_KEY` | hex 64 | Sí (`comun/seguridad.py`) | Firma JWT |
| API | `UI_ORIGENES_PERMITIDOS` | `https://<dns-stage>` | Sí (CORS) | Faltaba en v1 |
| Aprobación | `SEGREGACION_APROBACION` | `false` | Sí | Faltaba en v1; decisión del patrocinador |
| Redis | `REDIS_*` | `redis`, `6379`, secreto | Sí (`comun/cola.py`) | También interpolada en compose |
| LLM | `LLM_BASE_URL` | `http://ollama:11434` | Sí | Contenedor; v1 igual |
| LLM | `LLM_MODEL_PRINCIPAL` | `gpt-oss:20b` | Sí | v1 decía `[POR CONFIRMAR]` |
| LLM | `LLM_MODEL_EMBEDDINGS` | `bge-m3` | Sí | Igual al de indexación |
| LLM | `LLM_TIMEOUT_S` | `600` (stage) | Sí (`rag/cliente_llm.py`) | Tiempo máximo de una llamada a la IA. Si una generación larga lo supera, el análisis contable ya no falla: publica los hallazgos de las reglas con texto de respaldo |
| LLM | `LLM_NUM_THREAD` | `12` (stage) | Sí (`rag/cliente_llm.py`) | Hilos de CPU de Ollama en el chat. Medido en stage: 12 hilos = 2.3 tokens/s y 20 hilos = 1.3. Debe ser fijo (cambiarlo recarga el modelo) |
| Ollama | `OLLAMA_KEEP_ALIVE`, `OLLAMA_MAX_LOADED_MODELS`, `OLLAMA_NUM_PARALLEL` | `24h`, `3`, `1` | Servidor Ollama | Ahora también en `.env.stage.example`. Sin `OLLAMA_NUM_PARALLEL=1`, Ollama arrancó con 4 espacios paralelos (visto en el log) |
| LLM | `EMBEDDINGS_TIMEOUT_S`, `EMBEDDINGS_LOTE`, `EMBEDDINGS_REINTENTOS`, `EMBEDDINGS_KEEP_ALIVE` | `300`, `16`, `3`, `24h` | Sí (`rag/cliente_embeddings.py`) | P-15: antes el timeout era 30 s fijos (un embedding llegó a tardar 173.8 s). También aplica a la búsqueda del chat |
| LLM | `LLM_MODEL_ORTOGRAFIA` | sin definir | Sí (opcional) | Cae al principal |
| Ollama | `OLLAMA_KEEP_ALIVE`, `OLLAMA_MAX_LOADED_MODELS`, `OLLAMA_NUM_PARALLEL` | `24h`, `3`, `1` | Servidor Ollama | Llegan al contenedor `ollama` por `env_file` |
| Offline | `HF_HUB_OFFLINE`… `DO_NOT_TRACK` | `1` | Librerías | Faltaban en v1 |
| Qdrant | `QDRANT_*` | `qdrant`, `6333`, `agente_admin_kb_stage` | Sí | Colección propia de stage |
| PostgreSQL | `POSTGRES_*` | `postgres`, `5432`, usuario y secreto | Sí (`comun/db.py`) | También interpolada en compose |
| Objetos S3 | `MINIO_ENDPOINT` | `garage:3900` | Sí (`comun/almacenamiento.py`) | Garage v1.0.1 en stage (ADR-006 v2); región `us-east-1`, path-style. `localstack:4566` solo en local |
| Objetos S3 | `MINIO_BUCKET_CONOCIMIENTO` | `conocimiento` | Sí | Faltaba en v1 |
| Ortografía | `LANGUAGETOOL_LOCALE` | `es` | Sí | v1 decía `es-GT` → **error 400** |
| Ortografía | `LANGUAGETOOL_TIMEOUT_S` | `60` | Sí | Antes 20 s fijos: la primera petición tras un rato sin uso (arranque en frío de LanguageTool) vencía |
| Auth | `LDAP_*` | vacías | No | LDAP no implementado |
| Otras | `ORQUESTADOR_MAX_CONCURRENCIA`, `LLM_CONTEXT_WINDOW`, `OCR_DPI_MINIMO`, `DOCUMENTO_*` | 2, 8192, 300, 1024/90 | No | Documentales; el código usa valores fijos |
| Langfuse | `LANGFUSE_*` | secretos | Compose | Solo con `--profile observabilidad` |

## 3. Ajustes obligatorios en `infra/compose.stage.yml` (no son del `.env`, pero bloquean el arranque)

| # | Problema encontrado | Efecto | Corrección propuesta |
| --- | --- | --- | --- |
| 1 | El overlay define el servicio `minio`, pero `compose.yml` ya no lo tiene | `docker compose config` falla: servicio sin imagen | Reemplazar por el servicio `garage` (`dxflrs/garage:v1.0.1`, binds `/srv/agente/garage/{meta,data}`, `garage.toml` de solo lectura, sin puertos) y quitar `localstack` de stage (P-15 Bloque 5) |
| 2 | `ollama` limitado a `cpus: "1.50"` | El LLM usa 1.5 núcleos: muy lento | `cpus` = núcleos de la VM − 4 (ej. `"20"`) [POR CONFIRMAR con `nproc`] |
| 3 | `ollama` con `memory: 200G` y luego `64G`; `cpus: "8"` | La memoria superaba la RAM de la VM de 60 GB; con 20 vCPU, 8 CPU de límite hacen que Docker pause los 20 hilos de Ollama y la IA se vuelva muy lenta | VM actual: 20 vCPU y 121 GB → `cpus: "20"` (igual a los vCPU de la VM; si TI los cambia, cambiarlo también) y `memory: 80G` |
| 3b | `proxy` con `memory: 64G` | Límite desproporcionado para un proxy | `memory: 256M` |
| 4 | `red_interna` es `internal: true` | El contenedor `ollama` no tiene internet: `ollama pull` falla | Descargar modelos con un contenedor temporal (guía de modelos §5) |
| 5 | LocalStack como almacenamiento de stage | **Confirmado: perdió objetos al reiniciar** pese a `PERSISTENCE=1` | Resuelto con Garage (ADR-006 v2): persistencia tras reinicio y multiparte de 1 GB probadas |
| 6 | Permisos de `/srv/agente` | Prometheus (uid 65534) y Grafana (uid 472) no pueden escribir y el contenedor se reinicia | `sudo chown -R 65534:65534 /srv/agente/prometheus` y `sudo chown -R 472:472 /srv/agente/grafana` |
| 7 | Indexación de fuentes (P-15, ADR-010): aprobar encola la tarea en la cola `indexacion` | Sin un consumidor, la fuente se queda en "indexando" | Servicio `worker_indexacion` (concurrencia 1, misma imagen que `worker`); reconstruir la imagen (ahora incluye `curaduria`) y aplicar la migraciones `d41a9b7c5e20` y `e7b2c9a14f60` con `alembic upgrade head` (la segunda se detiene si hay fuentes duplicadas por ID y versión) |

### Garage (almacenamiento de objetos en stage)

- El `rpc_secret` se genera por ambiente (`openssl rand -hex 32`) y se escribe solo en `garage.toml` del servidor (copiado desde `infra/garage/garage.toml.example`); nunca va a Git.
- Después del primer `up -d garage`, ejecutar `infra/scripts/inicializar-garage.sh` (idempotente: layout, llave de acceso, buckets `conocimiento` y `documentos`) y copiar la llave a `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` en `.env.stage`.

## 4. Pasos únicos después del primer `up -d` (porque `APP_ENV=stage`)

```bash
srv$ cd /opt/agente/app/infra
srv$ alias dcs='docker compose --env-file ../.env.stage -f compose.yml -f compose.stage.yml'
# 1. Migraciones de BD (mismo comando que en local; ver docs/06-operacion/instalacion.md) [POR CONFIRMAR ruta de alembic.ini]
srv$ dcs exec api alembic upgrade head
# 2. Buckets S3
srv$ dcs exec api python -c "from comun import almacenamiento as a; c=a.obtener_cliente_s3(); [a.asegurar_bucket(c,b) for b in ('documentos','conocimiento')]; print('buckets OK')"
# 3. Área, roles y usuarios base (los mismos <rol>@local de desarrollo)
srv$ dcs exec api python -c "from comun.db import obtener_fabrica_sesion; from comun.semillas import sembrar_datos_de_prueba; print(list(sembrar_datos_de_prueba(obtener_fabrica_sesion()())))"
```

## 5. Riesgos

| ID | Riesgo | Mitigación |
| --- | --- | --- |
| R-ENV-01 | **Login con usuarios de prueba y contraseña pública** (`comun/seguridad.py`, AD/LDAP no implementado). Cualquiera en la red con la URL puede entrar | Stage solo con datos sintéticos/anonimizados; acceso por firewall a la red del piloto; implementar AD/LDAP o contraseñas por usuario antes de documentos reales (RF-01) |
| R-ENV-02 | Secretos en texto plano en el servidor | `chmod 600`, dueño el usuario de servicio, copia en gestor de secretos |
| R-ENV-03 | Cambiar `LLM_MODEL_EMBEDDINGS` sin reindexar | Errores de dimensión o búsquedas vacías en RAG |
| R-ENV-04 | `.env.stage.example` vuelve a desalinearse del código | Al agregar `os.environ.get("X")` en `src/`, actualizar las 3 plantillas `.env.*.example` en el mismo commit |
