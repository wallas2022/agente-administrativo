# Roles y permisos

**Versión:** 0.3.0
**Fecha:** 2026-10-09
**Relacionado con:** docs/01-requerimientos/01-requerimiento-formal.md §6, RF-01,02,13,16,18,19; RNF-02; RN-07; docs/05-prompts/P-12-usuarios-roles-menu-historial.md; docs/02-analisis/05-analisis-usuarios-roles-historial.md

Matriz rol × acción para los cinco roles operativos del sistema (el Patrocinador es un interesado de negocio, no opera el sistema — ver SRS §6).

> **v0.3 (2026-10-09, P-12):** la matriz de la sección siguiente ("Acción") es la vista narrativa, sin cambios de fondo. La vista operativa nueva es la de **§ Matriz recurso:acción** más abajo: cada fila es una fila real de la tabla `permiso` (`rol_id`, `recurso`, `accion`), sembrada por `comun.permisos.sembrar_permisos_por_defecto` y editable por el Administrador (Bloque 4, HU-23) salvo las filas protegidas. El Administrador y el Auditor siguen viendo todas las áreas (sin cambio); la segmentación por área de un recurso puntual (un documento, un análisis) es un mecanismo aparte, descrito en "Supuesto 2", y no se modela como permiso.

## Matriz de permisos

| Acción | Analista | Revisor/Aprobador | Curador de conocimiento | Administrador (TI) | Auditor |
| --- | --- | --- | --- | --- | --- |
| Autenticarse (RF-01) | Sí | Sí | Sí | Sí | Sí |
| Cargar documento (RF-03) | Sí (de su área) | No | No | No | No |
| Ejecutar análisis (CU-01..06) | Sí (de su área) | No | No | No | No |
| Ver hallazgos de un análisis propio | Sí | Sí | No | No | No |
| Ver hallazgos de análisis de su área | Sí | Sí | No | No | No |
| Decidir hallazgo: aceptar/rechazar/deshacer (RF-13) | **No** | Sí -- desde v0.9, también sobre lo que él mismo cargó por defecto (`SEGREGACION_APROBACION=false`); con `=true` vuelve a excluirse ese caso (RNF-02, RN-07) | No | No | No |
| Generar documento corregido / reporte PDF (RF-14, RF-15) | No (se genera automáticamente tras la decisión) | Dispara la generación al decidir | No | No | No |
| Cargar fuente de conocimiento (RF-16) | No | No | Sí (de su área) | No | No |
| Aprobar fuente de conocimiento (RF-16) | No | No | Sí (de su área, no puede autoaprobar su propia carga [POR CONFIRMAR si aplica]) | No | No |
| Editar glosario del área (RF-17) | No | No | Sí (de su área) | No | No |
| Administrar usuarios y roles (RF-02) | No | No | No | Sí | No |
| Configurar infraestructura/modelos/respaldos | No | No | No | Sí | No |
| Consultar historial de análisis con filtros (RF-18) | Sí (de su área) | Sí (de su área) | Sí (de su área) | Sí (todas) | Sí (todas) |
| Consultar bitácora de auditoría (RF-19) | No | No | No | Sí (lectura) | Sí (lectura) |
| Modificar o eliminar bitácora | No | No | No | No | No |
| Ver reporte "Ajustes autoaprobados" (RG-06, PP-09, v0.9) | No | No | No | Sí | Sí |

## Elemento · responsabilidad · tecnología

| Elemento | Responsabilidad | Tecnología |
| --- | --- | --- |
| Autenticación | Verifica identidad contra AD/LDAP o usuarios locales | `src/auth` (RF-01) |
| Autorización por rol | Aplica esta matriz en cada endpoint | `src/api` + `src/auth` (RBAC) |
| Segmentación por área | Restringe el alcance de datos visibles al área del usuario | `usuario.area_id` (ver docs/03-diseno/er/modelo-datos.md) |
| Segregación de funciones | Configurable (RN-07, `SEGREGACION_APROBACION`): bloquea autoaprobación solo si `=true`; con el valor por defecto, la marca y deja en bitácora en vez de bloquear | `src/api`, verificado en cada decisión (ver docs/03-diseno/secuencia/cu-07-aprobacion.md) |

## Supuestos

1. Un usuario tiene un único rol activo a la vez (ver docs/03-diseno/er/modelo-datos.md, supuesto 1); no hay combinación de roles en el piloto.
2. "De su área" significa que el alcance de datos se filtra por `area_id` del usuario, salvo Administrador y Auditor, que ven todas las áreas (necesario para su función).
3. El Curador no puede aprobar una fuente que él mismo cargó [POR CONFIRMAR si el SRS exige un segundo curador o si el mismo Curador puede autoaprobar su propia área — a diferencia de RN-07 (Revisor), el SRS no lo dice explícitamente para el Curador].
4. El Auditor y el Administrador tienen acceso de solo lectura a la bitácora; ningún rol, incluido Administrador, puede modificarla o eliminarla (RF-19 es append-only).
5. Esta matriz cubre los permisos de la entrega 1; los casos de uso de entrega 2 (CU-03, CU-04, CU-06) siguen el mismo patrón de "Analista ejecuta, Revisor decide".
6. v0.9 (2026-09-30): la segregación de funciones (fila "Decidir hallazgo") se volvió configurable por decisión del responsable del proyecto -- ver `docs/01-requerimientos/01-requerimiento-formal.md` §11 (RNF-02) y `docs/02-analisis/03-riesgos.md` (R-11).

## Matriz recurso:acción (v0.3, P-12)

Cada celda "Sí" es una fila sembrada en `permiso(rol_id, recurso, accion)`. 🔒 = protegida: el Administrador no puede editarla ni borrarla desde Configuración (HU-23) -- ni siquiera para su propio rol.

| Recurso:acción | Analista | Revisor | Curador | Administrador | Auditor |
| --- | --- | --- | --- | --- | --- |
| `analisis:crear` | Sí | No | No | Sí | No |
| `historial:propio` | Sí | Sí | Sí | Sí | Sí |
| `historial:area` | Sí | Sí | Sí | Sí | Sí |
| `historial:todas` | No | No | No | Sí | Sí |
| `hallazgos:decidir` | No | Sí | No | Sí | No |
| `conocimiento:ver` | No | No | Sí | Sí | Sí |
| `conocimiento:gestionar` | No | No | Sí | No | No |
| `conocimiento:aprobar` | No | No | Sí | No | No |
| `bitacora:ver` | No | No | No | Sí 🔒 | Sí 🔒 |
| `reportes:autoaprobados` | No | No | No | Sí | Sí |
| `usuarios:administrar` | No | No | No | Sí 🔒 | No |
| `roles:administrar` | No | No | No | Sí 🔒 | No |
| `areas:administrar` | No | No | No | Sí 🔒 | No |

Notas:
- `historial:area` lo tienen los 5 roles: para Analista/Revisor/Curador es el techo real (ven su área); para Administrador/Auditor es un filtro más dentro de lo que ya pueden ver con `historial:todas` (HU-21: pueden acotar a una sola área en vez de ver todas a la vez).
- `bitacora:ver` es la pantalla nueva de auditoría global (Bloque 2/HU-20), **no** el detalle de pasos de un análisis puntual (`GET /analisis/{id}/bitacora`, pantalla "Agente trabajando"): ese endpoint sigue gobernado por si el usuario puede ver ESE análisis (segmentación por área), no por este permiso -- no cambia con P-12.
- `conocimiento:ver` es de solo lectura (listar/previsualizar fuentes y glosario); `conocimiento:gestionar` (crear/editar/importar) y `conocimiento:aprobar` (aprobar/marcar obsoleta) son escritura, exclusivas del Curador -- sin cambio de fondo respecto a v0.2, solo ahora expresado como permisos en vez de `requiere_rol` fijo.
- `analisis:crear` cubre todo el flujo de carga (iniciar/partes/completar) de cualquier CU-01..06 -- es una sola acción de principio a fin, igual que ya la trataba la matriz narrativa ("Cargar documento" + "Ejecutar análisis" en una fila).

## Menú por rol (HU-20)

| Opción de menú | Permiso que la habilita | Analista | Revisor | Curador | Administrador | Auditor |
| --- | --- | --- | --- | --- | --- | --- |
| Nuevo análisis | `analisis:crear` | Sí | No | No | Sí | No |
| Historial | `historial:propio` (siempre presente si hay sesión) | Sí | Sí | Sí | Sí | Sí |
| Base de conocimiento | `conocimiento:ver` | No | No | Sí | Sí | Sí |
| Ajustes autoaprobados | `reportes:autoaprobados` | No | No | No | Sí | Sí |
| Bitácora | `bitacora:ver` | No | No | No | Sí | Sí |
| Configuración | `usuarios:administrar` **o** `roles:administrar` **o** `areas:administrar` | No | No | No | Sí | No |

La URL directa a una pantalla sin el permiso correspondiente muestra "Sin acceso" en la UI (no un redirect silencioso a `/`) y el endpoint que la respalda responde 403 -- el backend es la barrera real (RNF-02); el menú solo evita mostrar algo que de todas formas sería rechazado.

## Reglas de protección (HU-22, HU-23, R-P1, R-P4)

1. Un usuario nunca se borra, solo se desactiva (`usuario.activo = false`); no autodesactivarse.
2. El sistema rechaza desactivar o quitarle el rol Administrador al único Administrador activo que queda.
3. Las filas de `permiso` marcadas 🔒 en la matriz de arriba no se pueden editar ni borrar desde Configuración, bajo ningún rol.
4. "Restaurar matriz por defecto" (Configuración → Roles y permisos) vuelve a sembrar exactamente esta matriz v0.3, sin tocar usuarios ni áreas.
5. Un área con usuarios o documentos asociados no se puede eliminar (HU-24).
6. Toda alta/edición/desactivación de usuario, cambio de rol, cambio de permisos, restablecimiento/cambio de contraseña, bloqueo e inicio de sesión fallido queda en bitácora -- nunca la contraseña ni su hash (RNF-SEG-01).
