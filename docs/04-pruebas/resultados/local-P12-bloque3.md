# Resultados — P-12 (menú por permisos, historial, configuración), Bloque 3 (Historial)

**Versión:** 0.1.0
**Fecha:** 2026-10-09
**Relacionado con:** docs/05-prompts/P-12-usuarios-roles-menu-historial.md, docs/01-requerimientos/03-historias-de-usuario.md (HU-21), docs/04-pruebas/resultados/local-P12-bloque2.md

## Alcance

`GET /historial` reemplaza el stub "Próximamente" de la pantalla Historial: alcance (`propio`/`area`/`todas`, según el permiso `historial:*` de quien consulta), filtros (`desde`, `hasta`, `tipo_revision`, `estado`, `archivo`, `usuario_id`, `area_id`) y paginación. Cada fila trae quién lo corrió, su área, la duración (`fecha_fin - fecha_inicio`) y el número de hallazgos. UI según HU-21, con enlace al resultado de cada análisis.

## Backend: `GET /historial`

Distinto de `GET /analisis` (panel "Análisis recientes" de la pantalla 1, alcance fijo por rol): acá el alcance lo elige quien consulta, limitado por su permiso -- pedir `alcance=todas` sin `historial:todas` da 403; un `alcance` fuera de `propio|area|todas` da 422. `usuario_id`/`area_id` dejan a Administrador/Auditor acotar dentro de lo que ya ven con `historial:todas` (nota de roles-permisos.md v0.3). La duración y el número de hallazgos se calculan en el servidor (el segundo con una sola consulta agregada para los IDs de la página, no N+1). Usa los índices sembrados en el Bloque 1 (`ix_analisis_fecha_inicio`, `ix_documento_usuario_carga_area`).

13 pruebas nuevas (`tests/unit/test_historial.py`): alcance por defecto, alcance inválido (422), alcance sin permiso (403), alcance `area` sí/no cruza de área, alcance `todas` solo Administrador/Auditor, acotar `todas` por `area_id`, duración y número de hallazgos, análisis sin `fecha_fin` (duración `null`), filtros de tipo/estado/archivo, rango de fechas, paginación (página intermedia y última), página/tamaño inválidos (422).

## Frontend: `Historial.tsx`

| Elemento | Detalle |
| --- | --- |
| Selector de alcance | Solo aparece si el usuario tiene más de un permiso `historial:*` (Analista/Revisor/Curador, con un único alcance real, no ven el selector); cambiar de alcance vuelve a buscar de inmediato (HU-21). |
| Filtros | Fecha desde/hasta, tipo de revisión, estado, archivo -- se aplican con "Buscar", igual que Bitácora/Ajustes autoaprobados. |
| Tabla | Fecha, documento (enlace), tipo, estado (`EstadoBadge`, reutilizado), usuario, área, duración (formateada "X min Y s"), número de hallazgos. |
| Paginación | Anterior/Siguiente, 20 por página, con el total devuelto por el backend. |
| Enlace a cada análisis | `rutaDeAnalisis()` -- nuevo, en `utils/rutaAnalisis.ts`: mismo criterio que ya usaba `PanelAnalisisRecientes` (en proceso → "Agente trabajando", si no → Hallazgos). Se extrajo a un módulo compartido en vez de duplicar la función, que ya vivía igual en `PanelAnalisisRecientes.tsx`. |

7 pruebas nuevas (`Historial.test.tsx`): alcance por defecto al montar, selector oculto con un solo permiso, cambio de alcance dispara una nueva búsqueda, mensaje vacío, mensaje de error, paginación deshabilitada en los extremos, el documento enlaza a la ruta correcta.

## Validación en vivo (Docker + Postgres real)

Contra los ~100+ análisis reales acumulados en esta base de datos local (de los bloques y pruebas E2E de sesiones anteriores): `analista@local` sin `alcance` ve sus propios análisis (102, paginado), `alcance=todas` le da 403; `administrador@local` con `alcance=todas` ve el total real (112) con duración y conteo de hallazgos correctos; `alcance=rara` da 422.

## Resultado

| Ruta | Cambio | Prueba |
| --- | --- | --- |
| `src/api/main.py`, `esquemas.py` | `GET /historial` (alcance, filtros, paginación) | ok -- 13 passed |
| `src/ui/src/paginas/Historial.tsx` (nuevo) | Pantalla completa según HU-21 | ok -- 7 passed |
| `src/ui/src/utils/rutaAnalisis.ts` (nuevo) | `rutaDeAnalisis()` compartida con `PanelAnalisisRecientes` | ok (cubierto por las pruebas de ambos) |
| `src/ui/src/App.tsx` | `/historial` ya no es `Proximamente` | ok |

```
tests/unit (backend, suite completa): 574 passed en 272.52 s
ruff check / mypy: sin hallazgos
src/ui vitest (suite completa): 82 passed
src/ui tsc -b / oxlint: sin hallazgos (2 warnings preexistentes, no relacionados)
```

## Pendiente (explícitamente de otros bloques, no de este)

- Prueba de carga "historial ≤ 1 s con 10 000 análisis sintéticos" -- Bloque 5 (Pruebas y cierre), según el propio P-12.
- Cobertura E2E de "historial por alcance" -- también Bloque 5.
- Cuando el Bloque 2 señaló que "/" seguiría alojando el panel de análisis recientes hasta que Historial existiera de verdad: ya existe. Queda para un ajuste posterior (fuera de este bloque) decidir si gatear "/" por `analisis:crear` y dejar que Revisor/Curador/Auditor usen solo Historial para llegar a sus análisis -- no se cambia acá para no tocar UI fuera del alcance de este bloque.

¿Continúo con el Bloque 4 (Configuración del Administrador)?
