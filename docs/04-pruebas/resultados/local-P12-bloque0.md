# Resultados — P-12 (menú por permisos, historial, configuración), Bloque 0 (Red de seguridad)

**Versión:** 0.1.0
**Fecha:** 2026-10-09
**Relacionado con:** docs/05-prompts/P-12-usuarios-roles-menu-historial.md, docs/03-diseno/seguridad/roles-permisos.md v0.3

## Alcance

Matriz rol × endpoint con el comportamiento ACTUAL (antes de migrar `requiere_rol` → `requiere_permiso`): captura qué rol puede usar cada uno de los 27 endpoints de `src/api/main.py` hoy (200/403, no corrección funcional). Debe seguir en verde, sin cambiar ninguna aserción, después de cada bloque siguiente.

## Cobertura

| Grupo | Endpoints | Casos |
| --- | --- | --- |
| Solo rol (`requiere_rol`) | 17 (carga de documentos, decidir hallazgo, generar corregido, reportes autoaprobados, 10 de curaduría) | 17 × 5 roles = 85 |
| Rol + segmentación por área (`usuario_actual` + chequeo manual) | 6 (`/analisis/{id}`, hallazgos, bitácora, version-corregida, version-original, ocr-docx) | 6 × 5 roles = 30 |
| Caso especial (`/fuentes-conocimiento`, nunca 403, filtra por área) | 1 | 5 |
| **Total** | **24 endpoints únicos** | **120 (116 netos, 4 de "grupo solo-rol" también ejercitan parte del chequeo de área con una sola área)** |

No incluidos (fuera de este bloque, ver pendiente): `GET /analisis` (lista, nunca 403, filtra en el cuerpo), `GET /analisis/{id}/mejorar-stream` (SSE), `PUT /documentos/{id}/texto-ocr` (necesita cuerpo JSON válido para no confundir 422 de validación con 403 de rol).

## Hallazgo del diagnóstico confirmado por prueba

`GET /fuentes-conocimiento` es el único endpoint que **nunca** devuelve 403: filtra siempre por `usuario.area_id`, sin excepción para Administrador/Auditor (a diferencia de todos los demás). Queda como prueba explícita (`test_fuentes_conocimiento_filtra_por_area_sin_excepcion_de_rol`) para no perder este comportamiento sin darse cuenta al migrar a permisos.

## Problemas técnicos encontrados al construir la prueba (no de la API)

1. `create_engine("sqlite:///:memory:")` sin `StaticPool`/`check_same_thread=False` falla con "SQLite objects created in a thread can only be used in that same thread" -- el `TestClient` corre el endpoint en un threadpool distinto. Resuelto reutilizando el fixture `sesion_bd` ya existente (`tests/unit/conftest.py`), que ya lo resuelve.
2. `TestClient(main.app)` por defecto **relanza** cualquier excepción no capturada del endpoint como excepción de Python, no como respuesta 500 -- un error no relacionado con permisos (p. ej. `NoSuchKey` de S3 porque el fixture no sube contenido real para todos los endpoints) tapaba la aserción real de 403. Resuelto con `TestClient(main.app, raise_server_exceptions=False)`.

## Resultado

| Ruta | Cambio | Prueba |
| --- | --- | --- |
| `tests/unit/test_seguridad_matriz_rol_endpoint.py` (nuevo) | Matriz rol × endpoint (116 casos) + caso especial de `/fuentes-conocimiento` | **ok** -- 116 passed en 74 s |

```
tests/unit (suite completa, con el Bloque 0): 525 passed en 143.98 s
ruff check: sin hallazgos
```

## Pendiente (no bloqueante para el Bloque 1)

- `GET /analisis` (lista), `GET /analisis/{id}/mejorar-stream` (SSE) y `PUT /documentos/{id}/texto-ocr` quedaron fuera de la matriz explícita -- se pueden agregar si el Bloque 1 los toca, pero hoy ninguno cambia de `requiere_rol` (el primero y el último ya eran `usuario_actual` + chequeo manual).
