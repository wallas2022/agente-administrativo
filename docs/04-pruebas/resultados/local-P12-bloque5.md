# Resultados — P-12 (menú por permisos, historial, configuración), Bloque 5 (Pruebas y cierre)

**Versión:** 0.1.0
**Fecha:** 2026-10-09
**Relacionado con:** docs/05-prompts/P-12-usuarios-roles-menu-historial.md, docs/04-pruebas/resultados/local-P12-bloque0.md..bloque4.md

## Alcance

Cierre de P-12: confirmar en verde todo lo construido en los Bloques 0-4, agregar las dos pruebas que faltaban explícitamente (ningún hash expuesto, historial con 10,000 análisis en ≤1 s) y un caso E2E nuevo (menú por rol), y actualizar la documentación operativa y de pruebas.

## Checklist del Bloque 5

| Ítem pedido | Estado | Evidencia |
| --- | --- | --- |
| Matriz rol × endpoint (Bloque 0) en verde | **116/116**, sin cambiar ninguna aserción desde el diagnóstico original | re-ejecutada de forma aislada en este bloque |
| Menú por rol (E2E, un caso por rol) | **Nuevo** -- `src/ui/e2e/menu-por-rol.spec.ts`, 5/5 roles | ver tabla abajo |
| Historial por alcance | Ya cubierto en el Bloque 3 (13 pruebas: propio/área/todas, filtros, paginación) | [local-P12-bloque3.md](local-P12-bloque3.md) |
| Reglas de protección | Ya cubiertas en el Bloque 4 (22 pruebas: autodesactivación, último Administrador activo, permisos protegidos, área en uso) | [local-P12-bloque4.md](local-P12-bloque4.md) |
| Bloqueo por intentos | Ya cubierto en el Bloque 1 (`test_seguridad.py`) y Bloque 2 (`test_auth_endpoints.py`) | [local-P12-bloque1.md](local-P12-bloque1.md) |
| Ningún hash en respuestas ni bitácora | **Nuevo** -- `tests/unit/test_sin_hashes_expuestos.py`, 2 pruebas | ver detalle abajo |
| Historial ≤ 1 s con 10,000 análisis sintéticos | **Nuevo** -- `tests/unit/test_historial_rendimiento.py`, medido **0.039 s** | ver detalle abajo |

## Menú por rol (E2E)

`src/ui/e2e/menu-por-rol.spec.ts`: inicia sesión con cada uno de los 5 usuarios de prueba y compara el texto de los enlaces del menú lateral contra lo que permite la matriz real de `comun/permisos.py` (no el ejemplo narrativo de HU-20, que no lista "Nuevo análisis" ni "Base de conocimiento" para Administrador aunque sí tiene esos permisos -- discrepancia ya señalada en [local-P12-bloque2.md](local-P12-bloque2.md), pendiente de corregir en la propia historia de usuario).

| Rol | Menú verificado |
| --- | --- |
| Analista | Nuevo análisis, Historial |
| Revisor | Historial |
| Curador | Historial, Base de conocimiento |
| Auditor | Historial, Base de conocimiento, Ajustes autoaprobados, Bitácora |
| Administrador | Nuevo análisis, Historial, Base de conocimiento, Ajustes autoaprobados, Bitácora, Configuración |

## Ningún hash en respuestas ni bitácora

`tests/unit/test_sin_hashes_expuestos.py` busca el prefijo de bcrypt (`$2b$`) y los hashes reales de todos los usuarios sembrados en el cuerpo de `GET /usuarios`, `GET /auth/me` y `GET /bitacora`. La segunda prueba ejercita los cuatro flujos que sí escriben en bitácora -- crear usuario, editar usuario, restablecer contraseña, cambiar la propia contraseña -- y revisa el campo `detalle` de **todas** las filas (no solo las nuevas) contra los hashes vigentes y las contraseñas en texto plano usadas en la prueba (incluidas las dos contraseñas temporales generadas). Ninguna apareció.

## Historial con 10,000 análisis sintéticos

`tests/unit/test_historial_rendimiento.py` inserta 10,000 filas de `Documento` + `Analisis` con `sqlalchemy.insert(...)` (inserción masiva, no ORM objeto por objeto -- para que el propio setup no sea el cuello de botella que se quiere medir) y mide `GET /historial?alcance=todas` con `time.perf_counter()`. Resultado medido: **0.039 s** (umbral 1 s) -- los índices sembrados en el Bloque 1 (`ix_analisis_fecha_inicio`, `ix_documento_usuario_carga_area`) cumplen su propósito. Medido en SQLite en memoria (igual que el resto de la suite unitaria); [POR CONFIRMAR] el mismo umbral contra Postgres en stage, con datos reales en vez de sintéticos.

## Documentación actualizada

| Documento | Cambio |
| --- | --- |
| `docs/04-pruebas/plan-pruebas-prototipo.md` (v0.4→v0.5) | Dos filas nuevas en "Registro de resultados": PP-10 (permisos por área, validado por la matriz del Bloque 0) y PP-11 (bitácora completa sin contraseñas, validado por este bloque). |
| `docs/04-pruebas/estado-proyecto.md` | CU-09 y CU-10 pasan de "soporte base, [POR CONFIRMAR]" a "Completo (P-12)", con enlaces a los 5 documentos de resultados; nota de "qué falta" actualizada. |
| `docs/06-operacion/despliegue-stage-proxmox.md` (v1.2→v1.3) | Nueva sección "Primer Administrador (P-12, RF-01/RF-02)": comando `comun.crear_admin`, por qué los usuarios de prueba de `semillas.py` nunca deben sembrarse en stage, y una advertencia explícita de que Alembic no está en la imagen `api` (confirmado en el Bloque 1) -- para no repetir ahí el mismo error que ya se señaló en `configuracion-env-stage.md`. |
| `docs/04-pruebas/guion-demo-sandbox.md` (v0.1.0→v0.2.0) | Tabla de usuarios de prueba por rol y una nueva sección "P-12" con 5 pasos de demo (menú por rol, cambio de contraseña obligatorio, historial, bitácora, configuración). |

## Resultado

```
tests/unit (backend, suite completa): 605 passed en 266.28 s
tests/unit/test_seguridad_matriz_rol_endpoint.py (Bloque 0, aislado): 116 passed en 145.25 s
ruff check / mypy: sin hallazgos
src/ui/e2e (Playwright, --workers=1, 9 specs incl. menu-por-rol.spec.ts): 13/13 pasan
  (una corrida con todos los specs juntos marcó 1 falla transitoria en
  flujo-analista-revisor.spec.ts justo después de un spec de ~3.4 min;
  aislada, pasa en 9.8 s -- contención de recursos del entorno local, no
  una regresión, mismo patrón ya documentado en local-P12-bloque2.md)
```

## Cierre de P-12

Los 5 bloques de `docs/05-prompts/P-12-usuarios-roles-menu-historial.md` quedan completos: modelo y autenticación contra base de datos (Bloque 1), menú y rutas por permisos (Bloque 2), historial de análisis (Bloque 3), Configuración del Administrador (Bloque 4) y este cierre (Bloque 5). Pendientes explícitos, ninguno bloqueante:

- Corregir la tabla de ejemplo de HU-20 en `03-historias-de-usuario.md` para que coincida con la matriz real (señalado desde el Bloque 2).
- Gatear "/" por completo detrás de `analisis:crear` cuando el panel de "análisis recientes" dentro de esa pantalla deje de ser la única forma de Revisor/Curador/Auditor de llegar a sus análisis (hoy Historial ya existe, así que esto puede revisarse en una iteración de UX aparte -- no se tocó en este bloque para no mezclar un cambio de UI fuera del alcance de "pruebas y cierre").
- Levantar el contenedor `ui` propio de este proyecto requiere liberar el puerto 5173, ocupado por un contenedor de otro proyecto en esta máquina -- no se tocó (no es de este proyecto); se siguió validando con el servidor de desarrollo (`npm run dev`) en el puerto 5174.
- Validar el umbral de historial (≤1 s) contra Postgres real en stage, con datos reales en vez de sintéticos.

Entorno local reiniciado y verificado: `docker compose ... restart` dejó `api`, `orquestador`, `worker`, `postgres`, `redis`, `qdrant`, `ollama`, `languagetool`, `localstack` y `proxy` sanos; login y `/auth/me` confirmados en vivo tras el reinicio.
