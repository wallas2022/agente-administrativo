# Guía paso a paso — Actualizar stage al commit 9e0cca3 (15/10/2026)

**Versión:** 1.0
**Fecha:** 2026-10-15
**Relacionado con:** docs/06-operacion/guia-despliegue-p15-stage.md, docs/04-pruebas/resultados/stage-P15.md, tests/carga/README.md

Para quien opera stage (lab-ia-01). Esta guía lleva stage hasta el último commit de `main`. `dcs` es el alias de `docker compose --env-file ../.env.stage -f compose.yml -f compose.stage.yml`; todos los comandos `dcs` se ejecutan en `/opt/agente/app/infra`. `[ ]` marca datos que debes anotar al hacerlo.

## Qué trae esta actualización

| Cambio | Para qué | Requiere |
| --- | --- | --- |
| **Corrección del worker de indexación** (`f313d92`) | Antes la tarea fallaba con `ModuleNotFoundError: curaduria` y las fuentes quedaban en "indexando" para siempre | Reconstruir la imagen del worker |
| **Unicidad de fuentes** (`2f0cfe3`): `(fuente_id, versión)` único en la pantalla, la API, la base y el importador | Evita dos fuentes con el mismo ID y versión (y que un duplicado sobrescriba el archivo de la otra) | **Migración `e7b2c9a14f60`, que se detiene si ya hay duplicados** |
| **Chat** (`a74ac22`): ya no bloquea el servidor mientras espera a la IA, no guarda respuestas vacías y muestra las negritas | Con varios usuarios, una pregunta al chat paraba la API para todos | Reconstruir `api` y `ui` |
| Script de prueba de carga (`b3f2eb3`) y capturas de la presentación | Medir cuántos usuarios simultáneos soporta stage | Solo bajar el código |

Si en stage todavía **no** aplicaste P-15 (Garage, indexación asíncrona), empieza por el Paso A.

---

## Paso A. ¿Desde dónde partes? (5 min)

```bash
srv$ cd /opt/agente/app && git log --oneline -1 && git status --short
srv$ cd infra && dcs ps --format 'table {{.Service}}\t{{.Status}}'
srv$ dcs run --rm --no-deps -w /app/api api python -m alembic current
```

Anota: commit actual `[ ]`, ¿aparecen `garage` y `worker_indexacion`? `[ ]`, migración actual `[ ]`.

| Lo que ves | Caso | Qué hacer |
| --- | --- | --- |
| No aparecen `garage` ni `worker_indexacion`, o la migración es `7fcc343bac6f` | **Caso 1: P-15 sin aplicar** | Sigue [guia-despliegue-p15-stage.md](guia-despliegue-p15-stage.md) completa (ya incluye todo lo de esta actualización: hace el `git pull` al estado actual, los duplicados, ambas migraciones y las verificaciones). Después vuelve aquí solo al **Paso 8** (comprobaciones nuevas). |
| Aparecen `garage` y `worker_indexacion`, y la migración es `d41a9b7c5e20` | **Caso 2: P-15 ya aplicado** | Sigue desde el Paso 0 de esta guía. |
| Aparecen `garage` y `worker_indexacion`, y la migración es `e7b2c9a14f60` | Ya estás en la última | Solo las comprobaciones del Paso 8. |

El resto de la guía es el **Caso 2**.

## Paso 0. Respaldo (10 min)

1. **Snapshot de Proxmox** de la VM con el nombre `antes-actualizacion-1015`.
2. Respaldo de la base de datos:
   ```bash
   srv$ mkdir -p /srv/agente/backups
   srv$ dcs exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > /srv/agente/backups/db-antes-1015-$(date +%F).sql.gz
   srv$ ls -lh /srv/agente/backups/ | tail -2          # el archivo no debe pesar 0
   ```
3. Anota las fuentes y su estado (para comparar al final):
   ```bash
   srv$ dcs exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select fuente_id, version, estado, titulo from fuente_conocimiento order by fuente_id, version;"'
   ```

## Paso 1. Traer el código (5 min)

```bash
srv$ cd /opt/agente/app
srv$ git status --short                       # ¿hay cambios locales?
srv$ git stash push -m "local-antes-1015"     # solo si había cambios (los archivos sin seguimiento no se tocan)
srv$ git pull origin main
srv$ git log --oneline -3                     # arriba debe verse 9e0cca3 "docs(presentacion)..."
```

- Si `git pull` se queja de cambios locales en un archivo, revisa con `git stash show -p` si de verdad hacen falta; el repositorio ya trae todo lo de stage (Garage, alembic, límites).
- `.env.stage` y `/srv/agente/garage/garage.toml` no cambian: no están en Git.

## Paso 2. Buscar fuentes duplicadas — ANTES de migrar (5 min)

La migración nueva crea la restricción `UNIQUE (fuente_id, versión)`. Si hay filas repetidas, **se detiene y no borra nada**. Compruébalo antes (solo lee):

```bash
srv$ cd infra
srv$ dcs run --rm --no-deps api python -m curaduria.duplicados
```

> Este comando necesita la imagen de la API nueva (trae el módulo `curaduria.duplicados`). Si dice "No module named curaduria.duplicados", haz primero el Paso 3 (construir) y vuelve.

- **"No hay fuentes duplicadas…"**: sigue al Paso 3.
- **Lista uno o más grupos** (ID, título, estado, área, fecha y fragmentos de cada fila): decide cuál renombrar y corrígelo, por ejemplo:
  ```bash
  srv$ dcs exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "update fuente_conocimiento set fuente_id = '"'"'ID-NUEVO'"'"' where id = '"'"'<id de la fila>'"'"';"'
  ```
  Si la fila ya está **vigente**, además hay que actualizar el campo `fuente_id` de sus puntos en Qdrant (o marcarla obsoleta y volver a subir el archivo con otro ID, que es más simple). Repite el comando hasta que diga que no hay duplicados.

## Paso 3. Construir las imágenes (10–20 min)

```bash
srv$ dcs config > /dev/null && echo "compose OK"
srv$ dcs build api worker worker_indexacion orquestador ui
```

La construcción descarga paquetes y necesita salida a internet del **servidor** (no de los contenedores). Si no la tiene, construye en tu PC y carga las imágenes con `infra/scripts/empaquetar-offline.sh` y `cargar-en-stage.sh` (ver `despliegue-stage-proxmox.md` §5).

## Paso 4. Migrar la base de datos (5 min)

```bash
srv$ dcs run --rm --no-deps -w /app/api api python -m alembic current       # debe decir d41a9b7c5e20
srv$ dcs run --rm --no-deps -w /app/api api python -m alembic upgrade head
srv$ dcs run --rm --no-deps -w /app/api api python -m alembic current       # debe decir e7b2c9a14f60 (head)
```

Comprueba la restricción:

```bash
srv$ dcs exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\d fuente_conocimiento"' | grep ux_fuente_conocimiento
```

Deben aparecer `ux_fuente_conocimiento_id_version` (UNIQUE `fuente_id, version`) y `ux_fuente_conocimiento_una_vigente`.

Si `upgrade` falla con "No se puede crear la restricción UNIQUE…", la migración **lista los duplicados y no cambió nada**: vuelve al Paso 2.

## Paso 5. Levantar los servicios con el código nuevo (5 min)

```bash
srv$ dcs up -d
srv$ dcs ps --format 'table {{.Service}}\t{{.Status}}'
```

Espera a que `api`, `worker`, `worker_indexacion`, `orquestador` y `ui` estén `healthy` (hasta 1–2 minutos). Verifica el worker de indexación:

```bash
srv$ dcs logs --tail=40 worker_indexacion | grep -iE "ready|queues|error"
srv$ dcs exec worker_indexacion celery -A orquestador inspect registered 2>&1 | grep indexar_fuente
```

Debe aparecer `orquestador.tareas.indexar_fuente_conocimiento` y `ready`, sin `ModuleNotFoundError`.

## Paso 6. Rescatar fuentes que se quedaron en "indexando" (5 min)

Si antes de esta actualización alguna aprobación falló con el error del worker, esas fuentes siguen en `indexando`. Mira cuáles:

```bash
srv$ dcs exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select id, fuente_id, version, titulo, fecha_carga from fuente_conocimiento where estado = '"'"'indexando'"'"';"'
```

Solo las que **no estén realmente en proceso** (no hay un fragmento avanzando en `dcs logs -f worker_indexacion`) se pasan a error para poder reintentarlas desde la pantalla:

```bash
srv$ dcs exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "update fuente_conocimiento set estado = '"'"'error_indexacion'"'"', motivo_error = '"'"'Interrumpida por un fallo del worker (corregido); pulse Reintentar'"'"' where estado = '"'"'indexando'"'"' and id = '"'"'<id>'"'"';"'
```

Luego, en la pantalla de la base de conocimiento, pulsa **Reintentar** en cada una.

## Paso 7. Probar lo nuevo con una fuente pequeña (15 min)

1. **Indexación (worker corregido):** sube un PDF corto como `PRUEBA-1015` versión `1` y pulsa **Aprobar**. Debe pasar a "indexando: fragmento N de M" y luego a `vigente` (anota los segundos `[ ]`).
2. **Unicidad:** vuelve a escribir `PRUEBA-1015` con versión `1` en el formulario. Antes de subir el archivo debe aparecer "Ya existe PRUEBA-1015 versión 1; use otro ID o suba una nueva versión" y el botón **Subir nueva fuente** debe quedar bloqueado. Con versión `2` debe permitirlo ("Se registrará como una nueva versión…").
3. **Importador:** importa de nuevo la plantilla que ya cargaste: debe rechazarla indicando hoja, fila y columna ("Ya existe…").
4. Cuando termines, marca `PRUEBA-1015` como obsoleta para que no contamine las respuestas del chat.

## Paso 8. Comprobar que el chat ya no bloquea al servidor (10 min)

Es el cambio que más importa para la capacidad con varios usuarios.

1. En una ventana, entra al **Chat** y haz una pregunta larga (por ejemplo sobre una política); mientras responde...
2. En el servidor, consulta la API repetidas veces:
   ```bash
   srv$ TIMEFORMAT='%R s'
   srv$ for i in $(seq 1 12); do
          time dcs exec -T api python -c "import urllib.request as u; print(u.urlopen('http://localhost:8000/health', timeout=10).read())"
          sleep 5
        done
   ```
   Cada respuesta debe llegar en unos pocos segundos (aprox. 1–2 s, que es lo que tarda el propio `dcs exec`) aunque el chat siga "pensando". Antes de la corrección se quedaban esperando hasta que la IA terminaba (minutos).
3. Entra con otro usuario en otra ventana mientras la primera pregunta sigue en curso: el inicio de sesión debe responder al instante.
4. Las respuestas del chat deben mostrar las negritas (no `**texto**`) y, si el modelo no logra redactar, un mensaje que pide reformular la pregunta (ya no un cuadro vacío).

## Paso 9. Prueba de carga con usuarios simultáneos (opcional, 1–2 h)

Solo con la imagen ya actualizada (Pasos 3 a 5). Instrucciones completas en [`tests/carga/README.md`](../../tests/carga/README.md). Resumen:

```bash
srv$ cd /opt/agente/app/infra
srv$ read -s CARGA_PASSWORD && export CARGA_PASSWORD
srv$ dcs run --rm --no-deps -e CARGA_PASSWORD -v /opt/agente/app/tests:/tests api \
       python /tests/carga/carga_concurrente.py --base http://api:8000 \
       --email <usuario analista> --escenario ortografia --usuarios 1,3,5,10 \
       --salida /tests/carga/resultados-stage-ortografia.json
```

Haz primero `ortografia` y `chat` (rápidos) y deja `contable` para el final (con 10 usuarios puede tardar casi una hora, porque la IA atiende una petición a la vez). Mientras corre, mira el Dashboard → Recursos. **Usa un usuario de prueba y datos sintéticos**, nunca documentos reales.

## Paso 10. Cierre

- [ ] Snapshot `actualizacion-validada-1015` en Proxmox.
- [ ] Anota los resultados (segundos de la indexación, duplicados encontrados, tiempos del `/health` durante el chat, tabla de la prueba de carga) en `docs/04-pruebas/resultados/stage-P15.md`.

---

## Si algo falla

| Síntoma | Causa probable | Qué hacer |
| --- | --- | --- |
| `git pull` no avanza | Cambios locales en archivos versionados | `git status`; `git stash push -m ...`; vuelve a intentar |
| `dcs build` falla al descargar paquetes | El servidor no tiene salida a internet | Construir en la PC y cargar con `cargar-en-stage.sh` |
| `alembic upgrade` dice "No se puede crear la restricción UNIQUE…" | Hay fuentes duplicadas | Paso 2; no se borró nada |
| `worker_indexacion` en `Restarting` o la tarea falla con `ModuleNotFoundError` | Imagen vieja del worker | `dcs build worker_indexacion worker orquestador && dcs up -d --force-recreate worker_indexacion worker orquestador` |
| Una fuente sigue en "indexando" sin avanzar | Tarea perdida (worker reiniciado a mitad) | Paso 6 y **Reintentar** |
| La pantalla no muestra la comprobación de ID repetido | El navegador tiene la UI vieja en caché | Ctrl+F5; si sigue, `dcs build ui && dcs up -d ui` |
| El chat sigue congelando la API | La imagen de `api` no se reconstruyó | `dcs build api && dcs up -d --force-recreate api` |
| Cualquier otra falla grave | — | **Rollback** (abajo) |

## Rollback

1. **Rápido (todo):** restaurar el snapshot `antes-actualizacion-1015` de Proxmox.
2. **Solo el código:** `git checkout <commit-anterior>` (el que anotaste en el Paso A), `dcs build` y `dcs up -d`. Si ya migraste, antes de volver al código viejo quita la restricción: `dcs run --rm --no-deps -w /app/api api python -m alembic downgrade d41a9b7c5e20`.
3. **Base de datos:** si hiciera falta, restaurar `/srv/agente/backups/db-antes-1015-*.sql.gz`.
