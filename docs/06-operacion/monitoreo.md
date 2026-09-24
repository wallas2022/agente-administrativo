# Monitoreo

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** RNF-04, RNF-05, RNF-08, RNF-11, infra/monitoreo/prometheus.yml, docs/04-pruebas/casos-prueba/PP-12.md, PP-13.md

## Componentes

| Componente | Qué mide | Tecnología |
| --- | --- | --- |
| Prometheus | Métricas de los servicios (`api`, `orquestador`, infraestructura) | Prometheus (perfil `observabilidad`) |
| Grafana | Dashboards sobre las métricas de Prometheus | Grafana |
| Langfuse | Trazas de prompts/respuestas del LLM: tiempos, tokens, modelo, versión de prompt | Langfuse (RNF-06, RNF-11) |

En local, este componente es opcional (`--profile observabilidad`); en stage se asume activo.

## Métricas clave

| Métrica | Fuente | Umbral / alerta | Relacionado con |
| --- | --- | --- | --- |
| Tiempo de análisis por documento (p50/p90) | `api`/`orquestador` `/metrics` | Alerta si p90 > 10 min | RNF-04, PP-12 |
| Documentos procesados / errores por jornada | `orquestador` `/metrics` | Alerta si procesados < 50 o errores > 0 en jornada | RNF-05, PP-13 |
| Uso de disco de la VM | node/host | **Alerta al 70 % de uso** | RNF-08 (capacidad 4 TB), R-07 |
| Longitud de la cola de Redis | `redis` (exporter [POR CONFIRMAR]) | Alerta si crece sostenidamente | RNF-05 |
| Estado `healthy`/`unhealthy` de contenedores | Docker healthchecks | Alerta ante cualquier `unhealthy` | Todos los servicios (ver infra/compose.yml) |
| Conexiones salientes a internet | firewall/proxy de red | Alerta ante cualquier intento | RNF-01, PP-14 |
| Tokens/latencia por prompt | Langfuse | Sin umbral duro; insumo para ADR-001 (comparación de modelos) | RNF-11 |

La configuración base de scraping está en [infra/monitoreo/prometheus.yml](../../infra/monitoreo/prometheus.yml); los exporters de `postgres_exporter`, `redis_exporter` y `node_exporter` [POR CONFIRMAR] se agregan cuando se dimensione stage.

## Alertas

| Alerta | Condición | Severidad | Acción |
| --- | --- | --- | --- |
| Disco al 70 % | Uso de disco de la VM ≥ 70 % de 4 TB | Alta | Notificar a TI; revisar retención (RN-08) y tamaño real de documentos (R-07) |
| Tiempo de análisis fuera de umbral | p90 > 10 min sostenido | Media | Revisar carga de workers (RNF-05) y modelo LLM activo |
| Contenedor `unhealthy` | Healthcheck fallido > 3 reintentos | Alta | Revisar logs del contenedor; posible reinicio |
| Conexión saliente detectada | Cualquier intento de salida a internet desde `red_interna` | Crítica | Investigar de inmediato (violación de RNF-01) |

[POR CONFIRMAR] Canal de notificación de alertas (correo, chat interno, etc.) y responsable de guardia.

## Dashboards sugeridos (Grafana)

1. **Operación diaria**: documentos procesados, tiempo p50/p90, errores.
2. **Capacidad**: uso de disco, uso de RAM/CPU por servicio, longitud de cola.
3. **Calidad del modelo**: comparación de modelos (vínculo con Langfuse y docs/04-pruebas/plan-pruebas-prototipo.md §3).

## Pendientes

- [POR CONFIRMAR] Exporters adicionales (`postgres_exporter`, `redis_exporter`, `node_exporter`) y su despliegue.
- [POR CONFIRMAR] Canal y responsable de guardia para alertas críticas.
- [POR CONFIRMAR] Retención de las propias métricas de Prometheus (por defecto vs. ajustada a 90 días para alinear con RNF-12).
