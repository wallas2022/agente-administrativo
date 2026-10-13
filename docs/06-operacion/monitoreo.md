# Monitoreo

**Versión:** 0.2.0
**Fecha:** 2026-10-13
**Relacionado con:** RNF-04, RNF-05, RNF-08, RNF-11, ADR-009, infra/monitoreo/prometheus.yml, docs/04-pruebas/casos-prueba/PP-12.md, PP-13.md, docs/06-operacion/dashboard-administrador.md

> **v0.2 (2026-10-13, P-13):** `node-exporter` y `cAdvisor` ya están implementados (antes figuraban como pendientes); los jobs `api`/`orquestador` hacia `/metrics` -- que nunca existieron -- fueron eliminados de `prometheus.yml`. El consumo de tokens/duración del LLM ya no depende de Langfuse ni de Prometheus: se registra en la tabla `uso_llm` y se consulta desde el "Dashboard del Administrador" (ver [dashboard-administrador.md](dashboard-administrador.md)), una pantalla propia del agente distinta de Grafana.

## Componentes

| Componente | Qué mide | Tecnología |
| --- | --- | --- |
| node-exporter | CPU, memoria, disco y carga del host | prom/node-exporter (ADR-009) |
| cAdvisor | CPU y memoria por contenedor | gcr.io/cadvisor/cadvisor (ADR-009) |
| Prometheus | Scrapea node-exporter y cAdvisor cada 30 s, retención 15 días | Prometheus (perfil `observabilidad`) |
| Grafana | Dashboards sobre las métricas de Prometheus (vista detallada para TI) | Grafana |
| Langfuse | Trazas de prompts/respuestas del LLM: tiempos, tokens, modelo, versión de prompt | Langfuse (RNF-06, RNF-11) |

En local, Prometheus/Grafana/Langfuse/node-exporter/cAdvisor son opcionales (`--profile observabilidad`); en stage se asumen activos.

## Métricas clave

| Métrica | Fuente | Umbral / alerta | Relacionado con |
| --- | --- | --- | --- |
| CPU/RAM/disco del host | node-exporter → Prometheus | **Alerta al 70 % de uso de disco** | RNF-08 (capacidad 4 TB), R-07 |
| CPU/memoria por contenedor (vs. su límite) | cAdvisor → Prometheus | Memoria de Ollama ≥ 90 % de su límite | RNF-16, Dashboard del Administrador |
| Tokens, duración y timeouts por llamada al LLM/embeddings | Tabla `uso_llm` (RF-21) | Timeouts > 10 % en 24 h | RNF-15, Dashboard del Administrador |
| Longitud de la cola de Redis | `redis` (exporter [POR CONFIRMAR]) | Alerta si crece sostenidamente | RNF-05 |
| Estado `healthy`/`unhealthy` de contenedores | Docker healthchecks | Alerta ante cualquier `unhealthy` | Todos los servicios (ver infra/compose.yml) |
| Conexiones salientes a internet | firewall/proxy de red | Alerta ante cualquier intento | RNF-01, PP-14 |
| Tokens/latencia por prompt (traza individual) | Langfuse | Sin umbral duro; insumo para ADR-001 (comparación de modelos) | RNF-11 |

Las tres primeras alertas (disco, memoria de Ollama, timeouts del LLM) ya están calculadas e integradas en la pantalla "Dashboard" del propio agente -- ver [dashboard-administrador.md](dashboard-administrador.md) para cómo leerlas y qué hacer ante cada una, sin depender de que alguien sepa leer Grafana/PromQL. La configuración base de scraping está en [infra/monitoreo/prometheus.yml](../../infra/monitoreo/prometheus.yml); `postgres_exporter` y `redis_exporter` [POR CONFIRMAR] siguen pendientes de dimensionar en stage.

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

- [POR CONFIRMAR] Exporters adicionales (`postgres_exporter`, `redis_exporter`) y su despliegue.
- [POR CONFIRMAR] Canal y responsable de guardia para alertas críticas.
- [POR CONFIRMAR] Retención de las propias métricas de Prometheus (por defecto vs. ajustada a 90 días para alinear con RNF-12).
