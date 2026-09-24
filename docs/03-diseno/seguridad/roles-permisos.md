# Roles y permisos

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** docs/01-requerimientos/01-requerimiento-formal.md §6, RF-01,02,13,16,18,19; RNF-02; RN-07

Matriz rol × acción para los cinco roles operativos del sistema (el Patrocinador es un interesado de negocio, no opera el sistema — ver SRS §6).

## Matriz de permisos

| Acción | Analista | Revisor/Aprobador | Curador de conocimiento | Administrador (TI) | Auditor |
| --- | --- | --- | --- | --- | --- |
| Autenticarse (RF-01) | Sí | Sí | Sí | Sí | Sí |
| Cargar documento (RF-03) | Sí (de su área) | No | No | No | No |
| Ejecutar análisis (CU-01..06) | Sí (de su área) | No | No | No | No |
| Ver hallazgos de un análisis propio | Sí | Sí | No | No | No |
| Ver hallazgos de análisis de su área | Sí | Sí | No | No | No |
| Decidir hallazgo: aceptar/rechazar/deshacer (RF-13) | **No** | Sí, salvo si es el mismo que cargó el documento (RNF-02, RN-07) | No | No | No |
| Generar documento corregido / reporte PDF (RF-14, RF-15) | No (se genera automáticamente tras la decisión) | Dispara la generación al decidir | No | No | No |
| Cargar fuente de conocimiento (RF-16) | No | No | Sí (de su área) | No | No |
| Aprobar fuente de conocimiento (RF-16) | No | No | Sí (de su área, no puede autoaprobar su propia carga [POR CONFIRMAR si aplica]) | No | No |
| Editar glosario del área (RF-17) | No | No | Sí (de su área) | No | No |
| Administrar usuarios y roles (RF-02) | No | No | No | Sí | No |
| Configurar infraestructura/modelos/respaldos | No | No | No | Sí | No |
| Consultar historial de análisis con filtros (RF-18) | Sí (de su área) | Sí (de su área) | Sí (de su área) | Sí (todas) | Sí (todas) |
| Consultar bitácora de auditoría (RF-19) | No | No | No | Sí (lectura) | Sí (lectura) |
| Modificar o eliminar bitácora | No | No | No | No | No |

## Elemento · responsabilidad · tecnología

| Elemento | Responsabilidad | Tecnología |
| --- | --- | --- |
| Autenticación | Verifica identidad contra AD/LDAP o usuarios locales | `src/auth` (RF-01) |
| Autorización por rol | Aplica esta matriz en cada endpoint | `src/api` + `src/auth` (RBAC) |
| Segmentación por área | Restringe el alcance de datos visibles al área del usuario | `usuario.area_id` (ver docs/03-diseno/er/modelo-datos.md) |
| Segregación de funciones | Bloquea auto-aprobación (RN-07) | `src/api`, verificado en cada decisión (ver docs/03-diseno/secuencia/cu-07-aprobacion.md) |

## Supuestos

1. Un usuario tiene un único rol activo a la vez (ver docs/03-diseno/er/modelo-datos.md, supuesto 1); no hay combinación de roles en el piloto.
2. "De su área" significa que el alcance de datos se filtra por `area_id` del usuario, salvo Administrador y Auditor, que ven todas las áreas (necesario para su función).
3. El Curador no puede aprobar una fuente que él mismo cargó [POR CONFIRMAR si el SRS exige un segundo curador o si el mismo Curador puede autoaprobar su propia área — a diferencia de RN-07 (Revisor), el SRS no lo dice explícitamente para el Curador].
4. El Auditor y el Administrador tienen acceso de solo lectura a la bitácora; ningún rol, incluido Administrador, puede modificarla o eliminarla (RF-19 es append-only).
5. Esta matriz cubre los permisos de la entrega 1; los casos de uso de entrega 2 (CU-03, CU-04, CU-06) siguen el mismo patrón de "Analista ejecuta, Revisor decide".
