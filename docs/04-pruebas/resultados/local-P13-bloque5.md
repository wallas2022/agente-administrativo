# Resultados — P-13 (Dashboard del Administrador), Bloque 5 (Pruebas y cierre)

**Versión:** 0.1.0
**Fecha:** 2026-10-13
**Relacionado con:** docs/05-prompts/P-13-dashboard-administrador-consumo.md, RF-21, RF-22, RNF-15..18, docs/04-pruebas/resultados/local-P13-bloque1.md..bloque4.md, docs/04-pruebas/plan-pruebas-prototipo.md (PP-21..24)

## Alcance

Cierre de P-13: rendimiento con 100,000 registros sintéticos (RNF-16), permisos (solo Administrador, 403 al resto), ausencia de secretos en configuración (RNF-17) y sobrecarga del registro de uso (RNF-15). Actualización de `plan-pruebas-prototipo.md`, `estado-proyecto.md`, `docs/06-operacion` y el guion de demo.

## Hallazgo real durante este bloque: RNF-16 no se cumplía a 100,000 registros

Al escribir la prueba de rendimiento (`tests/unit/test_dashboard_rendimiento.py`) con 100,000 filas sintéticas de `uso_llm`, `calcular_consumo` tardó **2.58 s** -- por encima del umbral de 2 s. La causa: `calcular_consumo`/`calcular_consumo_por_usuario` (Bloque 3) traían todas las filas a Python (`.all()`) y agregaban ahí, en vez de agregar en SQL.

**Corrección** (`src/comun/dashboard.py`): se reescribieron ambas funciones para agregar en SQL (`GROUP BY`/`SUM`/`COUNT`/`COUNT(DISTINCT ...)`), dejando en Python solo el cálculo de "duración media del análisis" (HU-28) sobre los pares `(grupo, analisis_id)` DISTINCT -- acotado por el número real de análisis, no por el número de filas de uso. Resultado, medido dos veces:

| Medición | Antes | Después |
| --- | --- | --- |
| `calcular_consumo` (100,000 filas, SQLite en memoria) | 2.58 s | 0.31 s |
| `calcular_consumo_por_usuario` (100,000 filas, SQLite en memoria) | — | 0.04 s |
| `GET /admin/dashboard/consumo` (100,000 filas reales, Postgres real vía `COPY`, stack Docker real) | — | 0.24 s |
| `GET /admin/dashboard/usuarios` (ídem) | — | 0.17 s |

Las filas sintéticas insertadas contra el Postgres real se borraron al terminar la medición (confirmado: 100,000 filas borradas, el conteo de `/admin/dashboard/consumo` volvió a las 12 llamadas reales previas a la prueba).

## Resultados de pruebas (reales, no estimados)

| Caso (plan de pruebas) | Prueba | Resultado | Cumple |
| --- | --- | --- | --- |
| PP-21 (RNF-16) | `calcular_consumo`/`calcular_consumo_por_usuario` con 100,000 filas sintéticas | 0.31 s / 0.04 s (SQLite); 0.24 s / 0.17 s (Postgres real vía HTTP) | Sí (≤ 2 s) |
| PP-22 (permisos) | 4 endpoints × 4 roles no-Administrador (`test_dashboard_endpoints.py`) + menú (`menu-por-rol.spec.ts`) | 0 accesos permitidos fuera de Administrador (403 / "Sin acceso") | Sí |
| PP-23 (RNF-17) | `/admin/dashboard/configuracion` contra `.env.local.example` real | 0 variables con `PASSWORD`/`SECRET`/`KEY`/`TOKEN` expuestas | Sí |
| PP-24 (RNF-15) | `registrar_uso_llm`, 500 llamadas simuladas (SQLite en memoria) | 0.151 ms/llamada en promedio | Sí (≤ 20 ms) |

- `pytest tests/unit` (suite completa, incluyendo la reescritura de `comun/dashboard.py` y las 2 pruebas nuevas de rendimiento): **674 passed** (672 del Bloque 4 + 2 de rendimiento), cobertura 94 %, sin regresiones.
- `ruff check` / `mypy` sobre `comun/dashboard.py`: sin hallazgos.

## Documentación actualizada

| Archivo | Cambio |
| --- | --- |
| `docs/04-pruebas/plan-pruebas-prototipo.md` | v0.5→v0.6: filas PP-21..24 (casos de prueba) y sus resultados reales (registro de resultados). |
| `docs/04-pruebas/estado-proyecto.md` | v0.1.0→v0.2.0: sección nueva "Otras capacidades (transversales, sin CU dedicado)" con P-13 completo; fila ADR-009 agregada a la tabla de ADR (faltaba, pese a estar aceptado e implementado desde el Bloque 2). |
| `docs/06-operacion/monitoreo.md` | v0.1.0→v0.2.0: corregido (node-exporter/cAdvisor ya no son "pendientes", los jobs `/metrics` inexistentes ya no se mencionan como fuente real); referencia al nuevo `dashboard-administrador.md`. |
| `docs/06-operacion/dashboard-administrador.md` (nuevo) | Cómo leer cada pestaña del Dashboard y qué hacer ante cada una de las 3 alertas (disco, memoria de Ollama, timeouts del LLM). |
| `docs/04-pruebas/guion-demo-sandbox.md` | v0.2.0→v0.3.0: sección nueva "P-13 — Dashboard del Administrador" con el mismo formato que la sección de P-12. |

## Definición de terminado (P-13, contra la sección 10 del prompt)

- Cada llamada al LLM y a embeddings queda registrada con tokens, duración, usuario y resultado -- Bloque 1.
- El Administrador ve consumo por servidor/usuario/caso de uso/modelo, recursos del host/contenedores/Ollama y la configuración vigente sin secretos -- Bloques 2-4.
- Solo el Administrador accede; el resto recibe 403 -- confirmado en este bloque (PP-22).
- Funciona en stage sin internet en ejecución -- `[POR CONFIRMAR]`: no verificado contra un stage real (no existe todavía, ver ADR-005); los montajes de solo lectura y la ausencia de puertos publicados de `node-exporter`/`cAdvisor` (Bloque 2) están diseñados para ese requisito, pero la verificación en stage queda pendiente del despliegue real (sección 9 del prompt).

P-13 queda cerrado en ambiente local. ¿Hay algo más que ajustar antes de considerarlo terminado, o seguimos con el siguiente pendiente del proyecto?
