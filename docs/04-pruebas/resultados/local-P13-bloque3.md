# Resultados — P-13 (Dashboard del Administrador), Bloque 3 (API del dashboard)

**Versión:** 0.1.0
**Fecha:** 2026-10-12
**Relacionado con:** docs/05-prompts/P-13-dashboard-administrador-consumo.md, ADR-009, HU-26..30, RF-21/RF-22, RNF-15..18, docs/04-pruebas/resultados/local-P13-bloque1.md, local-P13-bloque2.md

## Alcance

Los 4 endpoints de solo-Administrador que exponen lo registrado en el Bloque 1 (`UsoLlm`) y lo recolectado en el Bloque 2 (Prometheus/cAdvisor/node-exporter): `GET /admin/dashboard/consumo` (HU-26), `/usuarios` (HU-27, con exportación CSV), `/recursos` (HU-29) y `/configuracion` (HU-30). Nuevo permiso `dashboard:ver`.

## Cambios

| Archivo | Cambio |
| --- | --- |
| `src/comun/permisos.py` | Permiso `dashboard:ver` agregado a `MATRIZ_PERMISOS_DEFECTO[ADMINISTRADOR]` y a `PERMISOS_PROTEGIDOS` (protegido, no editable desde Configuración → Roles, igual que `usuarios:administrar`). |
| `docs/03-diseno/seguridad/roles-permisos.md` | v0.3.0 → v0.4.0: fila `dashboard:ver` en la matriz recurso:acción y en "Menú por rol". |
| `src/api/Dockerfile` | `ARG`/`ENV` `APP_VERSION`, `GIT_COMMIT` (por defecto `sin-confirmar`) para que `/configuracion` pueda mostrarlos (HU-30) -- inyección automática del commit real queda `[POR CONFIRMAR]` (pendiente de un paso de build en CI/CD que hoy no existe). |
| `src/comun/dashboard.py` (nuevo) | Lógica pura: `calcular_consumo` (tarjetas, serie diaria, ranking por caso de uso/modelo, duración media del análisis), `calcular_consumo_por_usuario`, `consultar_recursos` (host + contenedores vía PromQL, Ollama vía `/api/ps` y `/api/tags`, degradación a `None`/`prometheus_disponible=false` si Prometheus no responde -- está apagado por defecto en local, ADR-009), `_calcular_alertas` (disco ≥70%, memoria de Ollama ≥90%, timeouts >10% en 24h -- RN de P-13 §5), `obtener_configuracion_vigente` (lista blanca `VARIABLES_CONFIGURACION_VISIBLES` de 14 variables reales, cruzadas contra `.env.local.example`; ninguna marcada como secreta por nombre). |
| `src/api/esquemas.py` | 10 esquemas nuevos (`RespuestaConsumo`, `FilaConsumoUsuarioEsquema`, `RespuestaRecursos`, `RespuestaConfiguracion`, etc.), sección "Dashboard del Administrador (P-13, Bloque 3)". |
| `src/api/main.py` | 4 endpoints nuevos bajo `requiere_permiso("dashboard:ver")`; `/usuarios` admite `?formato=csv` (adjunto, `Content-Disposition`). |
| `tests/unit/test_dashboard.py` (nuevo, 24 pruebas) | Lógica de `comun/dashboard.py` en aislamiento: agregaciones, filtros, degradación ante Prometheus/Ollama caídos, y la prueba RNF-17 que lee `.env.local.example` real y confirma que ninguna variable cuyo nombre contenga `PASSWORD\|SECRET\|KEY\|TOKEN` está en la lista blanca. |
| `tests/unit/test_dashboard_endpoints.py` (nuevo, 26 pruebas) | Los 4 endpoints a través de la API completa (`TestClient`): rechazo 403 para analista/revisor/curador/auditor en las 4 rutas, 200 para Administrador, datos reales de una fila `UsoLlm` sembrada, filtro por `area_id`, CSV con sus cabeceras, `/recursos` sin romperse cuando `httpx` falla, `/configuracion` sin filtrar secretos puestos a propósito en el entorno de la prueba. |

## Resultados de pruebas (reales, no estimados)

- `ruff check src tests`: **sin hallazgos**.
- `mypy src/api/main.py src/api/esquemas.py src/comun/dashboard.py`: **sin hallazgos**.
- `pytest tests/unit/test_dashboard.py tests/unit/test_dashboard_endpoints.py`: **50 passed**.
- `pytest tests/unit` (suite completa): **670 passed** (620 previos + 50 de este bloque), cobertura total 94%, sin regresiones.

## Validación en vivo (Docker real)

- Reconstruidas las imágenes `api`, `orquestador` y `worker` (`docker compose build`) y recreado el stack completo (`docker compose --env-file ../.env.local -f compose.yml -f compose.local.yml up -d`); los 11 contenedores del proyecto quedaron `healthy` (Prometheus/Grafana/node-exporter/cAdvisor del Bloque 2 **no** se levantan por defecto en local -- perfil `observabilidad`, ADR-009 -- consistente con lo documentado).
- Login real como `administrador@local` contra `http://127.0.0.1:8001` y llamadas reales a los 4 endpoints:
  - `GET /admin/dashboard/consumo` → `200`, tarjetas/series/rankings en cero (no hay filas `UsoLlm` en esta base aún -- comportamiento esperado, ya probado con datos sembrados en `test_dashboard_endpoints.py`).
  - `GET /admin/dashboard/usuarios` → `200`, lista vacía; con `?formato=csv` → `200`, `content-type: text/csv; charset=utf-8`, `content-disposition: attachment; filename=consumo_por_usuario.csv`.
  - `GET /admin/dashboard/recursos` → `200`, `"prometheus_disponible": false`, `host`/`contenedores`/`ollama` en `null`, `alertas: []` -- degradación correcta, sin error, con Prometheus apagado.
  - `GET /admin/dashboard/configuracion` → `200`, únicamente las 14 variables de la lista blanca, con los valores reales del `.env.local` de esta máquina (`LLM_PROVIDER=ollama`, `LLM_MODEL_PRINCIPAL=gpt-oss:20b`, etc.) -- ninguna contraseña/clave/token del `.env.local` real aparece en la respuesta.
  - `GET /admin/dashboard/consumo` con el token de `analista@local` → `403`, confirmando el permiso `dashboard:ver` en la API real (no solo en la base de datos de pruebas).

## Incidente durante la validación en vivo (resuelto, documentado por transparencia)

Al reconstruir y levantar el stack sin pasar `--env-file ../.env.local` (el `.env.local` del proyecto vive en la raíz, no en `infra/`), Redis arrancó con `requirepass` vacío y Compose abortó el resto del stack por dependencia fallida. Quedaron además 4 contenedores sueltos (`grafana`, `prometheus`, `node-exporter`, `cadvisor`) de una prueba anterior del Bloque 2 bajo el perfil `observabilidad`, que impidieron recrear la red limpiamente. Se eliminaron esos 4 contenedores sueltos (`docker rm -f`, sin tocar volúmenes ni datos) y se repitió el `up` con `--env-file ../.env.local -f compose.yml -f compose.local.yml`, que es la invocación correcta para este proyecto -- con eso el stack completo quedó sano. No se perdió ningún dato (Postgres/Qdrant no se recrearon con `-v`).

## Pendiente (explícitamente de otros bloques de P-13)

- Bloque 4 (Pantalla): menú "Dashboard" con las 4 pestañas, gráficos SVG, mensajes de "sin datos todavía".
- Bloque 5 (Pruebas y cierre): prueba sintética de 100,000 filas (RNF-16, ≤2s), prueba de que solo Administrador ve el menú/endpoints, medición explícita del costo de `registrar_uso_llm` por llamada (RNF-15, ≤20ms), actualización de `plan-pruebas`/`estado-proyecto`/`docs/06-operacion` y del guion de demo.
- Inyección automática de `GIT_COMMIT` en el build (hoy manual vía `--build-arg`, sin paso de CI/CD que lo automatice) -- `[POR CONFIRMAR]`.

¿Continúo con el Bloque 4 (Pantalla: menú "Dashboard" con pestañas Consumo/Usuarios/Recursos/Configuración)?
