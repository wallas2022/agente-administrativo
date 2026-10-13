# Resultados — P-13 (Dashboard del Administrador), Bloque 4 (Pantalla)

**Versión:** 0.1.0
**Fecha:** 2026-10-13
**Relacionado con:** docs/05-prompts/P-13-dashboard-administrador-consumo.md, ADR-009, HU-26..30, docs/04-pruebas/resultados/local-P13-bloque3.md

## Alcance

Pantalla "Dashboard" (menú solo visible con `dashboard:ver`), con 4 pestañas -- Consumo (HU-26, HU-28), Usuarios (HU-27), Recursos (HU-29, refresco cada 30 s) y Configuración (HU-30) -- sobre los 4 endpoints del Bloque 3. Gráficos en SVG propio (barras y línea), sin librerías nuevas, con texto alternativo y tabla equivalente por accesibilidad.

## Cambios

| Archivo | Cambio |
| --- | --- |
| `src/ui/src/componentes/GraficoBarras.tsx`, `GraficoLinea.tsx`, `Graficos.css` (nuevos) | Gráficos SVG propios reutilizables. `role="img"` + `aria-label` con el resumen de los datos (texto alternativo) y una tabla `<table>` visible debajo (tabla equivalente) -- no existía ningún patrón de gráficos en el proyecto, se creó de cero. |
| `src/ui/src/paginas/Dashboard.tsx`, `.css` (nuevos) | Contenedor de 4 pestañas, mismo patrón que `Configuracion.tsx` (`role="tablist"`/`"tab"`/`aria-selected`). |
| `src/ui/src/paginas/DashboardConsumo.tsx` (nuevo) | HU-26/28: filtros (fecha, área, caso de uso, modelo), tarjetas, línea de tokens por día, dos rankings (caso de uso / modelo) con gráfico de barras + tabla. Mensaje claro de "sin datos" cuando `llamadas === 0`. |
| `src/ui/src/paginas/DashboardUsuarios.tsx` (nuevo) | HU-27: tabla de consumo por usuario + botón "Exportar CSV" (reutiliza `api/descargas.ts`, ya existente en el proyecto). |
| `src/ui/src/paginas/DashboardRecursos.tsx` (nuevo) | HU-29: host/contenedores (Prometheus) y Ollama, con `setInterval` de 30 s. Alertas (`alertas[]`) siempre visibles arriba de las demás secciones. Mensajes claros y diferenciados cuando Prometheus no está disponible (default en local, ADR-009) vs. cuando Ollama no responde. |
| `src/ui/src/paginas/DashboardConfiguracion.tsx` (nuevo) | HU-30: tabla de variables (lista blanca) + versión/commit. |
| `src/ui/src/componentes/Layout.tsx`, `App.tsx` | Entrada de menú "Dashboard" (condicionada a `dashboard:ver`) y ruta `/dashboard` con `RutaProtegida`. |
| `src/ui/src/api/esquema.ts` | Regenerado (`npm run generar-tipos-api`) contra la API real -- único cambio aditivo, incorpora los 4 endpoints del Bloque 3. |
| `src/ui/e2e/menu-por-rol.spec.ts` | "Dashboard" agregado a la lista esperada para `administrador`. |
| `src/ui/src/paginas/Dashboard*.test.tsx` (5 archivos nuevos) | Pruebas unitarias (Vitest + Testing Library) de las 4 pestañas y su contenedor. |

## Corrección de un hallazgo real durante la validación en vivo (no cosmético)

Al validar la pestaña Recursos contra el stack Docker real (con Prometheus apagado, el caso por defecto en local), `GET /admin/dashboard/recursos` tardó **36 segundos** en responder: `_consultar_host`/`_consultar_contenedores` (Bloque 3) hacen ~10 consultas PromQL independientes, cada una con su propio `timeout=5.0` -- con el hostname `prometheus` sin resolver, cada consulta agota su timeout completo antes de rendirse. Esto es incompatible con el refresco automático de 30 s de este mismo bloque (la pantalla nunca terminaría de cargar antes del siguiente ciclo).

**Corrección:** se agregó `_prometheus_disponible()` en `src/comun/dashboard.py` -- una sola comprobación rápida (`GET /-/ready`, `timeout=1.5`) antes de lanzar las demás consultas; si Prometheus no responde, `host`/`contenedores` se devuelven como `None` de inmediato, sin las ~10 consultas restantes. Medido en el mismo stack real: **36 s → 8.3 s** (el resto es la latencia propia de los 2 llamados a la API de Ollama nativa de Windows, listando 5 modelos instalados -- fuera del alcance de este bloque). Se agregaron 2 pruebas nuevas a `tests/unit/test_dashboard.py` que verifican el corte temprano (una sola llamada a Prometheus cuando no responde) y que `_consultar_host`/`_consultar_contenedores` sí se ejecutan cuando Prometheus está disponible.

## Resultados de pruebas (reales, no estimados)

- `tsc -b` (type-check de la UI): sin errores.
- `npx playwright test e2e/menu-por-rol.spec.ts` (stack real): **5 passed** -- confirma que "Dashboard" solo aparece para Administrador.
- `vitest run` (UI, suite completa): **118 passed** (24 archivos) -- incluye las 24 pruebas nuevas de este bloque (Dashboard + 4 pestañas).
- `pytest tests/unit` (backend, suite completa): **672 passed** (670 del Bloque 3 + 2 de la corrección de `_prometheus_disponible`), cobertura 94%, sin regresiones.
- `npx playwright test` (E2E completo, stack real): **12 passed**, 1 falla (`cu05-validacion-en-segundo-plano.spec.ts`, no relacionado con el Dashboard) -- confirmado como *flake* por arranque en frío de `orquestador`/`worker` tras el rebuild de este bloque: re-ejecutado en aislamiento, **pasó en 4.8 min** (muy por encima del timeout de 30 s que falló en la corrida conjunta). No es una regresión de este bloque.
- `oxlint` no pudo ejecutarse en esta máquina: el binario nativo (`@oxlint/binding-win32-x64-msvc`) está bloqueado por una directiva de Control de aplicaciones de Windows, preexistente a este bloque y no relacionado con el código -- `[POR CONFIRMAR]` para quien administre esa política localmente.

## Validación en vivo (Docker real)

- Reconstruida y recreada la imagen `ui` (y `api`/`orquestador`/`worker` tras la corrección de latencia).
- Navegación real como `administrador@local`: las 4 pestañas cargan y muestran datos reales o su mensaje de "sin datos"/"no disponible" correspondiente (ver tabla de configuración con los 14 valores reales del `.env.local`, sin secretos).
- Auditoría de accesibilidad AA (axe-core, mismos estándares que `e2e/accesibilidad.spec.ts`) ejecutada manualmente sobre las pestañas Consumo y Recursos: **0 violaciones** en ambas.
- Script de validación manual (ad-hoc, como en bloques anteriores) creado, usado y eliminado al terminar -- no se commitea.

## Pendiente (explícitamente del Bloque 5)

- Prueba sintética de 100,000 filas (RNF-16, dashboard ≤2 s).
- Prueba de que solo Administrador ve el menú/endpoints (403 para el resto) -- ya cubierta en el backend (Bloque 3) y en el menú (este bloque); falta el cierre formal de RNF-16/RNF-15 en un documento de cierre.
- Medición explícita del costo de `registrar_uso_llm` por llamada (RNF-15, ≤20 ms).
- Actualización de `plan-pruebas`, `estado-proyecto`, `docs/06-operacion` (cómo leer el dashboard y qué hacer ante cada alerta) y del guion de demo.

¿Continúo con el Bloque 5 (Pruebas y cierre)?
