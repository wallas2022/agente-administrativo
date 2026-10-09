# Resultados — P-12 (menú por permisos, historial, configuración), Bloque 4 (Configuración del Administrador)

**Versión:** 0.1.0
**Fecha:** 2026-10-09
**Relacionado con:** docs/05-prompts/P-12-usuarios-roles-menu-historial.md, docs/01-requerimientos/03-historias-de-usuario.md (HU-22, HU-23, HU-24), docs/03-diseno/seguridad/roles-permisos.md v0.3 ("Reglas de protección")

## Alcance

Pantalla "Configuración" con tres pestañas (Usuarios, Roles y permisos, Áreas), cada una visible solo con su permiso (`usuarios:administrar`, `roles:administrar`, `areas:administrar` -- hoy los tres son exclusivos de Administrador). Reglas de protección de roles-permisos.md v0.3: nunca se borra un usuario, no autodesactivarse, siempre al menos un Administrador activo, permisos protegidos no editables, "Restaurar matriz por defecto", contraseña temporal mostrada una sola vez, todo cambio en bitácora sin contraseñas ni hashes.

## Refactor previo: regla de contraseña centralizada

`comun/seguridad.py` gana `password_valida()` y `generar_password_temporal()`. Antes la regla de fortaleza (≥10 caracteres, letras y números) estaba duplicada en `api/main.py` (cambiar contraseña) y `comun/crear_admin.py` (rescate de Administrador en stage) -- ambos ahora importan la misma función, así que un cambio de política futuro no puede quedar aplicado en un solo lugar. `generar_password_temporal()` usa `secrets` (no `random`) y siempre cumple `password_valida()`.

## Backend

| Endpoint | Regla |
| --- | --- |
| `GET /usuarios` | Lista completa (nunca `password_hash`). |
| `POST /usuarios` | Genera contraseña temporal (HU-22); `debe_cambiar_password=True`; rechaza correo duplicado y rol desconocido. |
| `PATCH /usuarios/{id}` | Nunca borra (no existe `DELETE /usuarios`); rechaza autodesactivarse; rechaza dejar sin ningún Administrador activo (desactivar o cambiar el rol del último); registra en bitácora solo qué campo cambió. |
| `POST /usuarios/{id}/restablecer-password` | Nueva contraseña temporal, `debe_cambiar_password=True`, desbloquea y resetea intentos fallidos. |
| `GET /permisos` | Matriz completa (5 roles × 13 recurso:acción = 65 celdas), marca protegidas. |
| `PUT /permisos` | Otorga/revoca una celda; rechaza recurso:acción desconocido (422) y cualquier intento sobre una fila protegida (403, en cualquier sentido). |
| `POST /permisos/restaurar` | Vuelve exactamente a la matriz v0.3 (`comun.permisos.restaurar_matriz_por_defecto`, ya existía desde el Bloque 1). |
| `GET /areas`, `POST /areas`, `PATCH /areas/{id}` | Listar, crear y renombrar; nombre único (insensible a mayúsculas). |
| `DELETE /areas/{id}` | 409 si el área tiene usuarios o documentos asociados (HU-24). |

22 pruebas nuevas (`tests/unit/test_configuracion_admin.py`): rechazo por rol en los tres recursos, contraseña temporal que realmente funciona para entrar, correo/rol duplicados o inválidos, autodesactivación rechazada, dejar sin Administrador activo rechazado (tanto por desactivación como por cambio de rol), desactivar a OTRO Administrador si queda uno activo sí se permite, bitácora sin datos sensibles, restablecer contraseña, matriz completa, otorgar/revocar aplica de inmediato (verificado releyendo `/auth/me`), permiso protegido rechazado, recurso:acción desconocido rechazado, restaurar matriz, crear/renombrar área, nombre duplicado rechazado, área con usuarios o documentos no se elimina, área sin usar sí se elimina.

## Frontend

| Pieza | Detalle |
| --- | --- |
| `Configuracion.tsx` | Pestañas filtradas por `tienePermiso`, con la primera disponible activa por defecto. |
| `ConfiguracionUsuarios.tsx` | Tabla con rol/área editables inline (`<select>` → `PATCH` inmediato) y casilla de activo; formulario de alta; "Restablecer contraseña" por fila; banner de contraseña temporal (una sola vez, con botón "Cerrar"). |
| `ConfiguracionPermisos.tsx` | Matriz recurso:acción × rol con casillas; las protegidas aparecen deshabilitadas (`title` explica por qué); "Restaurar matriz por defecto" pide confirmación (`window.confirm`, sin librerías nuevas) antes de llamar al endpoint. |
| `ConfiguracionAreas.tsx` | Alta, renombrado inline y eliminación; el 409 del backend se traduce a un mensaje claro ("tiene usuarios o documentos asociados"). |

19 pruebas nuevas (`Configuracion.test.tsx` + una por pestaña): filtrado de pestañas por permiso, flujo completo de alta de usuario con contraseña temporal, edición inline, restablecer contraseña, matriz de permisos y su protección, confirmación de restaurar, alta/renombrado/duplicado/conflicto de áreas.

`Proximamente.tsx` se eliminó: ya no lo usa ninguna pantalla (Historial y Configuración son ahora reales).

## Validación en vivo (Docker + Postgres real)

Contra la base local real: `GET /permisos` devuelve las 65 celdas esperadas (5 × 13); se creó un usuario de prueba, se inició sesión con su contraseña temporal (funcionó), y se desactivó al cerrar la prueba (nunca se borró, como exige la regla); se creó y eliminó un área de prueba sin uso (204) y se confirmó que "Contabilidad" (en uso) no se puede eliminar (409); se otorgó y revocó `analista:conocimiento:ver` y se confirmó que un permiso protegido (`administrador:usuarios:administrar`) se rechaza con 403; `GET /bitacora` confirmó las entradas `usuario_creado` y `usuario_editado` sin ningún dato sensible.

## Resultado

| Ruta | Cambio | Prueba |
| --- | --- | --- |
| `comun/seguridad.py` | `password_valida()`, `generar_password_temporal()` (regla centralizada) | ok -- 6 passed |
| `comun/crear_admin.py` | Reusa `password_valida` en vez de duplicarla | ok (sin cambio de comportamiento) |
| `api/main.py`, `esquemas.py` | `/usuarios`, `/permisos`, `/areas` (HU-22, HU-23, HU-24) | ok -- 22 passed |
| `src/ui/src/paginas/Configuracion*.tsx` (nuevos) | Pestañas Usuarios / Roles y permisos / Áreas | ok -- 19 passed |
| `src/ui/src/paginas/Proximamente.tsx` | Eliminado (sin uso) | ok |
| `src/ui/src/App.tsx` | `/configuracion` ya no es un stub | ok |

```
tests/unit (backend, suite completa): 602 passed en 232.40 s
ruff check / mypy: sin hallazgos
src/ui vitest (suite completa): 101 passed
src/ui tsc -b: sin hallazgos
src/ui oxlint: sin hallazgos nuevos (3 warnings más de la misma categoría ya tolerada --
  "set-state-in-effect" en un fetch-on-mount, igual que PanelAnalisisRecientes.tsx desde antes de P-12)
```

## Pendiente (explícitamente de otros bloques)

- Pruebas de Bloque 5: matriz rol × endpoint (Bloque 0) en verde con los endpoints nuevos, E2E "un caso por rol" para el menú, reglas de protección también a nivel E2E, "ningún hash en respuestas ni bitácora" como prueba explícita de todo el sistema (hoy solo verificado puntualmente), guion de demo con usuarios por rol.
- No se agregó un límite de longitud ni confirmación "¿seguro?" al editar rol/área/activo desde la tabla de Usuarios (aplican de inmediato al cambiar el `<select>`/casilla) -- consistente con que el propio backend ya rechaza los casos peligrosos (autodesactivación, último Administrador); se puede revisar en una iteración de UX si hace falta una confirmación adicional.

¿Continúo con el Bloque 5 (Pruebas y cierre)?
