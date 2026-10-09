# Resultados — P-12 (menú por permisos, historial, configuración), Bloque 1 (Modelo y autenticación)

**Versión:** 0.1.0
**Fecha:** 2026-10-09
**Relacionado con:** docs/05-prompts/P-12-usuarios-roles-menu-historial.md, docs/03-diseno/seguridad/roles-permisos.md v0.3, docs/04-pruebas/resultados/local-P12-bloque0.md

## Alcance

Migración del rol/permisos de "fijos en código" a "en base de datos": login contra `usuario.password_hash` (bcrypt), bloqueo por intentos fallidos, JWT con `usuario_id` (ya no email/rol), `requiere_permiso("recurso:accion")` leyendo la tabla `permiso`, y `python -m comun.crear_admin` para el primer Administrador en stage. La matriz del Bloque 0 (116 casos) debía seguir en verde sin cambiar ninguna aserción: así fue.

## Cambios de modelo y migración

| Tabla/columna | Cambio |
| --- | --- |
| `usuario` | + `password_hash`, `debe_cambiar_password`, `intentos_fallidos`, `bloqueado_hasta`, `ultimo_acceso` |
| `permiso` | + restricción única `(rol_id, recurso, accion)` |
| `analisis` | + índice en `fecha_inicio` (para el Bloque 3, historial) |
| `documento` | + índice en `(usuario_carga_id, area_id)` (para el Bloque 3) |

Migración `7a01fd7275ed_autenticacion_y_permisos_p12.py` (down_revision `c3f7a1d9e824`), aplicada contra el Postgres local real.

## Permisos (`src/comun/permisos.py`)

13 pares `recurso:accion` sembrados según la matriz v0.3 de `roles-permisos.md`, con 5 marcados como protegidos (`PERMISOS_PROTEGIDOS`, regla de protección del Bloque 4). `sembrar_permisos_por_defecto` es idempotente; `restaurar_matriz_por_defecto` borra y re-siembra exactamente v0.3.

## Autenticación (`src/comun/seguridad.py`)

- `autenticar_usuario`: bcrypt, bloqueo tras 5 intentos fallidos por 15 min (`LIMITE_INTENTOS_FALLIDOS`, `MINUTOS_BLOQUEO`), reseteo de intentos al expirar el bloqueo o loguear con éxito.
- JWT: `{"sub": <usuario_id>}`, ya no lleva email ni rol -- un cambio de rol se refleja de inmediato sin volver a loguearse, porque `requiere_permiso` consulta la base en cada request.
- `requiere_rol`/`_nombre_rol` ahora leen `usuario.rol.nombre` desde la base; 17 endpoints migrados de `requiere_rol` a `requiere_permiso` sin cambiar ningún resultado del Bloque 0.

## Endpoints nuevos

| Endpoint | Función |
| --- | --- |
| `GET /auth/me` | usuario, rol, área, permisos (lista `recurso:accion`), `debe_cambiar_password` |
| `POST /auth/cambiar-password` | valida contraseña actual, exige ≥10 caracteres con letra y dígito, registra en bitácora (sin contraseñas/hashes) |
| `python -m comun.crear_admin` | idempotente, pide contraseña por consola (`getpass`), siembra permisos del rol |

## Bugs reales encontrados al validar contra Docker/Postgres (no en SQLite)

1. **Migración no aplicada**: tras reconstruir las imágenes, la API entraba en bucle de reinicio (`UndefinedColumn: usuario.password_hash`) porque Alembic no corre dentro de los contenedores (no está instalado ahí) -- hay que correrlo desde el host. Corregido ejecutando la migración desde `.venv` del host contra el Postgres expuesto en el puerto 5433.
2. **Usuarios de prueba preexistentes sin contraseña**: con la migración ya aplicada, el login seguía fallando para los 5 usuarios `<rol>@local` reales de esta base local -- se crearon en sesiones anteriores a `password_hash`, y `sembrar_datos_de_prueba` solo asignaba la contraseña a usuarios **nuevos**, nunca a uno ya existente. Corregido con una rama de "relleno" (`elif usuario.password_hash is None`) que completa `password_hash`/`debe_cambiar_password` en filas preexistentes sin tocar una contraseña ya cambiada (HU-25). Cubierto por dos pruebas nuevas en `tests/unit/test_semillas.py`.

## Verificación en vivo (Docker + Postgres real, no simulada)

- Login `analista@local` / `cambiar123` → 200; `GET /auth/me` → `permisos: ["analisis:crear","historial:area","historial:propio"]`, coincide con la matriz v0.3.
- Login `administrador@local` → `GET /auth/me` muestra los 11 permisos, incluidos los protegidos (`areas:administrar`, `roles:administrar`, `usuarios:administrar`) y `bitacora:ver`.
- 5 intentos fallidos seguidos como `auditor@local` → 401 cada uno; el 6to intento, con la contraseña correcta, sigue en 401 con `"Usuario bloqueado hasta <fecha> por demasiados intentos fallidos"`.
- `python -m comun.crear_admin --email ... --nombre ... --area Contabilidad` (contraseña por `getpass`) → crea el usuario y le siembra los permisos de Administrador; usuario de prueba eliminado de la base real al terminar la verificación.

## Resultado

| Ruta | Cambio | Prueba |
| --- | --- | --- |
| `src/comun/modelos.py` | columnas de autenticación en `Usuario`, restricción única en `Permiso`, índices en `Analisis`/`Documento` | ok |
| `src/api/migraciones/versions/7a01fd7275ed_...py` | migración Alembic (aplicada contra Postgres local real) | ok |
| `src/comun/permisos.py` | matriz de permisos v0.3, siembra idempotente, restaurar a default | ok -- 6 passed |
| `src/comun/seguridad.py` | login con bcrypt, bloqueo por intentos, JWT con `usuario_id` | ok -- 11 passed |
| `src/comun/semillas.py` | siembra permisos; relleno de `password_hash` para usuarios preexistentes | ok -- 6 passed |
| `src/api/esquemas.py`, `src/api/main.py` | `requiere_permiso`, `GET /auth/me`, `POST /auth/cambiar-password`, 17 endpoints migrados | ok |
| `src/comun/crear_admin.py` | comando para el primer Administrador en stage | ok -- 5 passed |
| `tests/unit/test_auth_endpoints.py` (nuevo) | `/auth/me`, `/auth/cambiar-password`, bloqueo end-to-end | ok -- 9 passed |
| `tests/unit/test_seguridad_matriz_rol_endpoint.py` | adaptado a `crear_token_acceso(usuario_id=...)`, mismo resultado que el Bloque 0 | ok -- 116 passed (sin cambios de comportamiento) |

```
tests/unit (suite completa): 552 passed en 198.93 s
ruff check: sin hallazgos
mypy: sin hallazgos
```

## Pendiente

- UI aún no consume `/auth/me`, `permisos` ni `debe_cambiar_password` (Bloque 2).
- `docs/06-operacion/configuracion-env-stage.md` (fuera del alcance de P-12, agregado por el usuario como contexto) sugiere `dcs exec api alembic upgrade head`, que no funcionaría tal como está escrito porque Alembic no está instalado en esa imagen -- igual que se encontró aquí para local. No se modifica ese documento en este bloque por estar fuera de alcance; queda señalado para cuando se revise la guía de stage.

¿Continúo con el Bloque 2 (Menú y rutas por permisos)?
