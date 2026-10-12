# Resultados — P-13 (Dashboard del Administrador), Bloque 2 (Métricas de infraestructura)

**Versión:** 0.1.0
**Fecha:** 2026-10-12
**Relacionado con:** docs/05-prompts/P-13-dashboard-administrador-consumo.md, ADR-009, docs/04-pruebas/resultados/local-P13-bloque1.md

## Alcance

`node-exporter` (métricas del host) y `cAdvisor` (métricas por contenedor) agregados a `infra/compose.yml`, con sus límites de recursos en `compose.stage.yml`; `prometheus.yml` corregido (los jobs `api`/`orquestador` apuntaban a `/metrics` que nunca existió) y configurado con scrape cada 30 s y retención de 15 días.

## Cambios

| Archivo | Cambio |
| --- | --- |
| `infra/compose.yml` | Servicios `node-exporter` (prom/node-exporter:v1.8.2) y `cadvisor` (gcr.io/cadvisor/cadvisor:v0.49.1) -- montajes de solo lectura (`/proc`, `/sys`, `/`, `docker.sock`), sin puertos publicados, en `red_interna`. `prometheus` gana `--storage.tsdb.retention.time=15d` y `depends_on` de los dos exporters. |
| `infra/compose.local.yml` | `node-exporter`/`cadvisor` quedan bajo el mismo perfil opcional `observabilidad` que ya usan `prometheus`/`grafana`/`langfuse` (sin Prometheus corriendo, no tiene sentido tenerlos levantados aparte) -- límites bajos (0.10-0.15 CPU, 64-128M). |
| `infra/compose.stage.yml` | Límites de recursos para ambos (0.25 CPU / 128-256M) -- son exporters sin datos persistentes que respaldar, mismo patrón que el resto de servicios de monitoreo de este archivo. En stage **no** quedan bajo ningún perfil (siempre activos, igual que `prometheus`/`grafana` ahí). |
| `infra/monitoreo/prometheus.yml` | Elimina los jobs `api`/`orquestador` (`/metrics` nunca existió, confirmado al revisar el código -- ADR-009 decide no agregarlo en esta iteración); agrega jobs `node-exporter` y `cadvisor`; `scrape_interval`/`evaluation_interval` de 15s a 30s. |

## Validación en vivo (Docker real, con `--profile observabilidad`)

- `node-exporter` y `cadvisor` healthy; Prometheus los scrapea correctamente (los 3 targets -- `prometheus`, `node-exporter`, `cadvisor` -- en estado `up`).
- Consulta real contra Prometheus: `node_memory_MemAvailable_bytes` devuelve un valor plausible de esta máquina (~11.3 GB disponibles); `container_last_seen` devuelve series para los 8 contenedores corriendo en ese momento.
- `--storage.tsdb.retention.time=15d` confirmado en el comando real del contenedor (`docker inspect`).
- `docker compose ... config --quiet` valida sin errores tanto el overlay local como el de stage (este último con una copia temporal de `.env.stage.example` solo para la validación, luego eliminada -- `compose.stage.yml` no se puede validar de forma nativa hoy por un problema **preexistente, no de este bloque**: tiene una sección `minio:` que ya no existe en `compose.yml` base, reemplazado por `localstack` desde el 25-sep-2026. Queda señalado para quien revise `compose.stage.yml`, fuera de este bloque).

## Hallazgo (descartado tras investigar): `red_interna` con acceso a internet en local

Al probar `node-exporter` recién creado, se confirmó que SÍ tenía salida a internet real (`wget http://example.com` funcionó) pese a que `compose.yml` declara `red_interna: internal: true`. La investigación inicial sugería una red mal creada (drift de un `docker compose up` anterior) y se recreó la red completa (`down` sin `-v`, sin pérdida de datos, y `up -d` de nuevo) para corregirlo -- **innecesariamente**: `compose.local.yml` sobreescribe `internal: false` a propósito, con un comentario explícito ("en local SÍ hay internet, para `ollama pull`, `pip install`, etc."), y `compose.stage.yml` no lo toca (ahí sí queda `internal: true`, RNF-01 se cumple donde corresponde). Confirmado revisando ambos overlays: no era un bug. Se deja registrado acá como corrección del propio diagnóstico de esta sesión, no como hallazgo real.

## Pendiente (explícitamente de otros bloques de P-13)

- `GET /admin/dashboard/recursos` (Bloque 3) todavía no consulta estas métricas vía PromQL -- por ahora solo están disponibles en Prometheus/Grafana directamente.
- `postgres_exporter`/`redis_exporter` quedan como `[POR CONFIRMAR]` en `prometheus.yml` (no pedidos explícitamente por P-13 §6, fuera de alcance de este bloque).
- La discrepancia `minio`/`localstack` en `compose.stage.yml` (preexistente) no se corrigió -- no es de este bloque ni de P-13.

¿Continúo con el Bloque 3 (API del dashboard: `GET /admin/dashboard/consumo`, `/usuarios`, `/recursos`, `/configuracion`, permiso `dashboard:ver`)?
