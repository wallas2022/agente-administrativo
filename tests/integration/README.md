# tests/integration/

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** docs/04-pruebas/plan-pruebas-prototipo.md

Pruebas de integración de extremo a extremo (carga → análisis → revisión → aprobación) contra los servicios declarados en `infra/compose.yml`. Sin pruebas de pytest automatizadas todavía.

En L2 se verificó manualmente (no como test reproducible) que `worker` consume la cola real (Redis) y transiciona `documento`/`analisis`/`bitacora` en el Postgres real del stack local — ver docs/04-pruebas/resultados/local-L2.md. Formalizar esa verificación como prueba de pytest (marcada para saltarse si los servicios no están arriba) queda pendiente.
