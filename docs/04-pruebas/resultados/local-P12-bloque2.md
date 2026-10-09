# Resultados — P-12 (menú por permisos, historial, configuración), Bloque 2 (Menú y rutas por permisos)

**Versión:** 0.1.0
**Fecha:** 2026-10-09
**Relacionado con:** docs/05-prompts/P-12-usuarios-roles-menu-historial.md, docs/03-diseno/seguridad/roles-permisos.md v0.3, docs/04-pruebas/resultados/local-P12-bloque1.md

## Alcance

El menú y las rutas de la UI se construyen desde `GET /auth/me` (permisos reales, no un rol fijo). Sin el permiso de una pantalla, la opción no aparece en el menú y la URL directa muestra "Sin acceso". Pantalla de cambio de contraseña obligatoria (HU-25) y voluntaria. Rol y área visibles junto al usuario. Nueva opción "Bitácora" (Administrador/Auditor, solo lectura).

## Backend: `GET /bitacora`

Único endpoint nuevo de este bloque -- auditoría global de solo lectura, gateada por `requiere_permiso("bitacora:ver")`, con filtros `fecha_desde`, `fecha_hasta`, `usuario_email`, `accion`. Distinto de `GET /analisis/{id}/bitacora` (detalle de pasos de un análisis puntual, sigue gobernado por segmentación de área, no por este permiso). 7 pruebas nuevas (`tests/unit/test_bitacora_global.py`): rechazo por rol, acceso de Administrador/Auditor, sin exponer hash de contraseña, filtros combinados.

## Frontend

| Pieza | Cambio |
| --- | --- |
| `ContextoAuth.tsx` | `Usuario` ahora trae `id`, `area`, `permisos`, `debeCambiarPassword` (antes solo `email`/`rol`); tras el login hace `GET /auth/me` para completar el perfil; nuevo `tienePermiso(...permisos)` y `recargarPerfil()`. El token vive en un `ref` (no en estado) para que el primer `/auth/me` tras el login ya viaje con el token nuevo, no con uno de un render anterior. |
| `RutaProtegida.tsx` | `rolesPermitidos` → `permisoRequerido` (uno o varios, OR entre ellos). Sin el permiso, renderiza `SinAcceso` en la misma URL (no un redirect silencioso). Si `debeCambiarPassword`, redirige a `/cambiar-password` sin importar el permiso pedido. |
| `SinAcceso.tsx` (nuevo) | Pantalla fija para el caso anterior. |
| `CambiarPassword.tsx` (nuevo) | HU-25: aviso cuando la contraseña es temporal, valida la confirmación en el cliente, llama `POST /auth/cambiar-password` y recarga el perfil. También sirve para un cambio voluntario (enlace en el panel de usuario). |
| `Bitacora.tsx` (nuevo) | Filtros de fecha/usuario/acción sobre `GET /bitacora`, mismo patrón que `ReporteAjustesAutoaprobados.tsx`. |
| `Layout.tsx` | El menú se arma filtrando `OPCIONES_MENU` por `tienePermiso(...)` en vez de una lista fija; agrega "Bitácora"; muestra `rol · área` y un enlace "Cambiar contraseña". |
| `App.tsx` | Cada ruta protegida declara su `permisoRequerido` (`analisis:crear` se maneja aparte, ver Decisión de diseño); `/cambiar-password` nueva, fuera del `Layout`. |

## Decisión de diseño: "/" no se restringe por permiso

`NuevoAnalisis.tsx` (ruta "/") aloja hoy dos cosas: el formulario de carga y el panel "Análisis recientes" (`PanelAnalisisRecientes`) -- y ese panel es, mientras el Historial real (Bloque 3) siga siendo "Próximamente", la **única** forma que tienen Revisor/Curador/Auditor de llegar a un análisis propio o de su área (confirmado por `flujo-analista-revisor.spec.ts`, que depende de que el Revisor encuentre ahí el análisis del Analista). Gatear toda la ruta "/" con `analisis:crear` les habría mostrado "Sin acceso" y roto ese flujo ya existente.

Se optó por: la ruta "/" sigue accesible con solo sesión iniciada; `NuevoAnalisis.tsx` oculta el formulario de carga (y no llama a `/fuentes-conocimiento`) si `tienePermiso("analisis:crear")` es falso, dejando solo el panel -- que ya está correctamente segmentado por área en el backend (`GET /analisis`), así que no hay fuga de datos. El menú sí oculta "Nuevo análisis" para quien no tiene el permiso (HU-20 se cumple ahí). Queda señalado para el Bloque 3: cuando exista el Historial real, "/" puede gatearse por completo y la navegación a análisis recientes se muda a Historial.

## Hallazgo de documentación (no corregido en este bloque, fuera de alcance)

La tabla de ejemplo de HU-20 (`docs/01-requerimientos/03-historias-de-usuario.md`) no incluye "Nuevo análisis" ni "Base de conocimiento" para Administrador, pero la matriz operativa real (`roles-permisos.md` v0.3, § "Matriz recurso:acción", y `comun/permisos.py`) sí le da `analisis:crear` y `conocimiento:ver`. Como el menú se construye desde los permisos reales de `/auth/me` (instrucción explícita de este bloque), la UI sigue la matriz real, no el ejemplo de HU-20 -- Administrador ve ambas opciones. Se deja señalado para corregir la tabla de HU-20 en un cambio de documentación aparte.

## Problemas técnicos encontrados al validar (no de la lógica de permisos)

1. **Puerto 5173 ocupado por un proyecto ajeno**: `playwright.config.ts` usa `http://127.0.0.1:5173` (el puerto del servicio `ui` de este proyecto, `infra/compose.local.yml`), pero ese contenedor no estaba corriendo -- en su lugar, un contenedor Docker de otro proyecto sin relación ("Sistema de Gestión de Gastos", `gastos-frontend-local`) ocupaba ese puerto. Las primeras 8 pruebas E2E fallaron todas esperando el campo "Correo" porque Playwright probó la aplicación equivocada. Se validó manualmente contra el servidor de desarrollo (`npm run dev`) ya corriendo en el puerto 5174, cambiando `baseURL` solo de forma temporal para la corrida y revirtiéndolo después -- no se tocó el contenedor ajeno ni se modificó el valor commiteado.
2. **Contención del worker de Celery al correr E2E en paralelo**: con 5 workers de Playwright en paralelo, las 3 pruebas que procesan un análisis contable real (CU-01) agotaron su tiempo de espera esperando "Ver hallazgos" -- `infra-worker-1` llegó a 1 GiB/1 GiB de memoria (su límite) durante la corrida. Repetidas en serie (`--workers=1`), las 8 pruebas pasan en 47.6 s. No es una regresión de este bloque; es un límite de recursos del entorno local, ya documentado como riesgo de infraestructura (ver ADR-005).

## Resultado

| Ruta | Cambio | Prueba |
| --- | --- | --- |
| `src/api/main.py`, `src/api/esquemas.py` | `GET /bitacora` (auditoría global, permiso `bitacora:ver`) | ok -- 7 passed |
| `src/ui/src/auth/ContextoAuth.tsx` | Perfil completo tras login, `tienePermiso`, `recargarPerfil` | ok -- 4 passed |
| `src/ui/src/auth/RutaProtegida.tsx` | `permisoRequerido`, "Sin acceso" en la misma URL, redirect a cambiar contraseña | ok -- 5 passed |
| `src/ui/src/paginas/SinAcceso.tsx` (nuevo) | Pantalla de acceso denegado | ok |
| `src/ui/src/paginas/CambiarPassword.tsx` (nuevo) | HU-25, obligatorio y voluntario | ok -- 4 passed |
| `src/ui/src/paginas/Bitacora.tsx` (nuevo) | Auditoría global con filtros | ok -- 3 passed |
| `src/ui/src/componentes/Layout.tsx` | Menú por permisos, rol + área, enlace cambiar contraseña | ok -- 6 passed |
| `src/ui/src/paginas/NuevoAnalisis.tsx` | Oculta el formulario sin `analisis:crear`, conserva el panel | ok (cubierto por E2E) |
| `src/ui/src/App.tsx` | Rutas con `permisoRequerido` por pantalla | ok |
| `src/ui/e2e/*.spec.ts` | 8 pruebas existentes, sin cambios de aserciones (solo el helper de login, más robusto al destino) | ok -- 8/8 passed |

```
tests/unit (backend, suite completa): 561 passed en 510.45 s
ruff check / mypy: sin hallazgos
src/ui vitest (suite completa): 75 passed
src/ui tsc -b / oxlint: sin hallazgos (2 warnings preexistentes, no relacionados)
src/ui Playwright E2E (8 specs, --workers=1): 8 passed en 47.6 s
```

## Pendiente

- Corregir la tabla de ejemplo de HU-20 en `03-historias-de-usuario.md` para que coincida con la matriz real (ver "Hallazgo de documentación").
- Cuando el Bloque 3 (Historial) exista de verdad, gatear por completo "/" con `analisis:crear` y mover la navegación a análisis recientes a la pantalla de Historial.
- El contenedor `ui` propio de este proyecto (`infra/compose.local.yml`) no se levantó en esta sesión por el conflicto de puerto con un proyecto ajeno -- no bloquea este bloque (se validó por fuera), pero queda pendiente para cuando se necesite el entorno 100% contenedorizado.

¿Continúo con el Bloque 3 (Historial)?
