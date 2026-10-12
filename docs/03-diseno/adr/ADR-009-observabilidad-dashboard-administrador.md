# ADR-009 — Observabilidad del piloto: node-exporter + cAdvisor + tabla propia `uso_llm` (sin reemplazar Langfuse)

**Versión:** 1.0
**Fecha:** 2026-10-12
**Relacionado con:** RF-02, RF-19, RNF-04, RNF-05, RNF-06, RNF-11, R-02, R-07, R-11, ADR-005, docs/05-prompts/P-13-dashboard-administrador-consumo.md

## Estado

Propuesta.

## Contexto

P-13 pide un Dashboard del Administrador con cuatro vistas: consumo de LLM/embeddings, uso por usuario, recursos de infraestructura (host + contenedores + Ollama), y configuración vigente. Hoy:

- `rag/cliente_llm.py` y `rag/cliente_embeddings.py` descartan las métricas que Ollama ya devuelve en cada respuesta (`prompt_eval_count`, `eval_count`, `total_duration`, `load_duration`, etc.) -- solo se queda con el texto/vector.
- `infra/monitoreo/prometheus.yml` apunta a `/metrics` de `api` y `orquestador` que **no existen**; no hay `node-exporter` (métricas de host) ni `cAdvisor` (métricas por contenedor) -- RNF-11 ("Registro de prompts, tiempos, errores y consumo de recursos") nunca se implementó.
- **Langfuse ya existe** en `infra/compose.yml` (perfil `observabilidad`, desactivado por defecto), con su propia Postgres y ClickHouse -- pensado para trazar y depurar llamadas de LLM (prompts, respuestas, latencias por span). No cubre, ni está pensado para cubrir, agregaciones por usuario/área/caso de uso con filtros de fecha ni los datos de recursos de host/contenedor que pide HU-26..30 -- son propósitos distintos (depuración de trazas individuales vs. reporte agregado para el Administrador).

## Decisión

1. **Tabla propia `uso_llm` en el Postgres de negocio** (no Langfuse) para registrar cada llamada al LLM y a embeddings con usuario, área, análisis y caso de uso -- es lo que HU-26..28 necesitan consultar con filtros e índices simples, sin depender del perfil `observabilidad` (que sigue apagado por defecto) ni de una base ClickHouse aparte. Langfuse se mantiene sin cambios, como herramienta complementaria de depuración para quien la active, no como fuente del dashboard.
2. **Agregar `node-exporter` y `cAdvisor`** a `infra/compose.yml` (red interna, sin puertos publicados al host, montajes de solo lectura: `/proc`, `/sys`, `/` para node-exporter; `/var/run/docker.sock`, `/sys/fs/cgroup`, `/var/lib/docker` para cAdvisor) y sus límites de recursos en `compose.stage.yml`, siguiendo el mismo patrón `deploy.resources.limits` ya usado por `grafana`/`prometheus` ahí (livianos: `cpus: "0.25"`, `memory: "128M"`-`"256M"`).
3. **Corregir `prometheus.yml`**: quitar los jobs de `/metrics` de `api`/`orquestador` que nunca existieron (no se expondrá un endpoint de métricas propio en esta iteración -- los datos de LLM salen de la tabla `uso_llm` vía la API, no de Prometheus), agregar los jobs de `node-exporter`/`cAdvisor`, scrape cada 30 s, retención 15 días (R-D5/R-16).
4. **Alternativas descartadas**:
   - *Montar `docker.sock` directamente en la API para leer stats de contenedores*: innecesario y de mayor superficie de ataque -- cAdvisor ya expone esto vía HTTP interno sin que la API toque el socket de Docker.
   - *Leer `psutil` dentro de cada contenedor*: solo vería sus propios límites, no los del host ni los de otros contenedores -- no sirve para HU-29 (vista de todos los contenedores a la vez).
   - *Reemplazar Langfuse por `uso_llm`*: descartado -- son complementarios (ver Contexto); no se apaga ni se quita Langfuse.

## Consecuencias

- Dos piezas nuevas de infraestructura (`node-exporter`, `cAdvisor`) en `red_interna`, sin acceso a internet ni puertos publicados (RNF-01, RNF-19 -- P-13 §5) -- mismo patrón de aislamiento que el resto del stack.
- `uso_llm` crece sin límite salvo retención (P-13 no define una por ahora; se deja [POR CONFIRMAR] como pendiente de este ADR, ver Pendientes del Bloque 1).
- `cliente_llm.py`/`cliente_embeddings.py` necesitan una forma de exponer las métricas de Ollama sin romper a los ~2 puntos de llamada reales (`api/main.py`, `orquestador/tareas.py`) que hoy solo esperan texto/vector -- se resuelve con funciones `_con_metricas` nuevas que las funciones actuales envuelven (ver Bloque 1), no cambiando su firma pública.
- Grafana sigue siendo la vista detallada para TI (ya existente, sin cambios); el Dashboard del Administrador es una vista nueva, propia de la aplicación, con los datos que un Administrador necesita sin tener que aprender PromQL.
