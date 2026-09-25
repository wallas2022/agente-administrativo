# Resultados — L2 Esqueleto de aplicación

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** docs/03-diseno/c4/02-contenedores.md, docs/03-diseno/c4/03-componentes-orquestador.md, docs/03-diseno/er/modelo-datos.md, docs/03-diseno/estados/estados-analisis.md

## Alcance

Paquete compartido `src/comun/` (modelos SQLAlchemy, BD, seguridad, cola, almacenamiento, semillas) usado por `src/api` y `src/orquestador`; API FastAPI real (auth, carga por partes, análisis); tarea de Celery que transiciona estados y registra bitácora; migraciones Alembic del modelo ER completo. Sin validadores de negocio todavía (Sprint 1).

## Pruebas y cobertura

```
34 passed en 18-28 s
Cobertura total: 95 % (mínimo exigido: 70 %)
```

| Módulo | Cobertura |
| --- | --- |
| comun/modelos.py, comun/almacenamiento.py, comun/seguridad.py, comun/semillas.py | 100 % |
| api/esquemas.py | 100 % |
| api/main.py | 93 % |
| comun/cola.py | 85 % (rama de `send_task` real no se ejercita en unitarias) |
| comun/db.py | 62 % (la construcción de engine/sesión real se ejercita en la integración manual, no en unitarias con SQLite) |
| orquestador/tareas.py | 86 % |

`ruff check src tests` y `mypy src`: sin errores.

## Migraciones (Alembic)

Migración `7eab2d96069e_esquema_inicial` generada por autogenerate desde `comun/modelos.py` y **aplicada contra el Postgres real** del stack local (`localhost:5433`, ver infra/compose.local.yml). Verificado con `\dt`: las 15 tablas del modelo ER (`docs/03-diseno/er/modelo-datos.md`) más `alembic_version` existen en la base de datos.

## Integración real (no mockeada)

Con `orquestador`/`worker` reconstruidos y corriendo (`compose.local.yml`, build context ahora `../src` para compartir `comun/` — ver Dockerfiles), se probó el flujo completo **sin mocks**:

1. Se insertaron un `Documento` y un `Analisis` reales en el Postgres del stack (vía `docker exec` en `worker`).
2. Se encoló la tarea real con `comun.cola.encolar_analisis` (Celery + Redis reales).
3. El `worker` la consumió y transicionó los estados.

Resultado verificado con SQL directo:

| Verificación | Resultado |
| --- | --- |
| `documento.estado` tras el análisis | `en_revision` |
| `analisis.estado` / `fecha_fin` | `completado` / con marca de tiempo |
| `bitacora` | 2 filas: `analisis_iniciado`, `analisis_completado` |

## Hallazgos de esta fase

1. **`orquestador` y `worker` eran redundantes.** El servicio `orquestador` (F1) solo imprimía un mensaje y terminaba, generando un bucle de reinicio constante bajo `restart: unless-stopped`. Corregido para que quede en espera (sin bucle); se deja como esqueleto para un futuro scheduler tipo Celery beat (p. ej. el job periódico de retención de RN-08/RNF-12), documentado en el propio `__main__.py`. La orquestación real corre en `worker` (proceso Celery).
2. **`python:3.12-slim` no trae `curl`.** El healthcheck de `api` (heredado de F1) lo usaba; cambiado a `urllib` de la librería estándar para no agregar paquetes del sistema.
3. **Build context compartido.** `api` y `orquestador`/`worker` ahora comparten `src/comun/` — el build context de ambos pasó de `src/api`/`src/orquestador` a `src/` (con `dockerfile:` explícito), y los Dockerfiles copian `comun/` además de su propio paquete.
4. **Autenticación separada del modelo de datos.** Los usuarios locales de prueba (RF-01) viven en `comun/seguridad.py` (fixtures, un usuario por rol); `comun/semillas.py` crea la fila `Usuario` correspondiente en la base de datos la primera vez que se necesita, para que `Documento.usuario_carga_id` tenga una fila real que referenciar. Es una simplificación deliberada del esqueleto: cuando exista AD/LDAP real, este puente dejará de ser necesario.

## Pendiente

- MinIO sigue sin poder descargarse (ver docs/04-pruebas/resultados/local-L1.md); `api` no se pudo levantar como contenedor real en esta fase (depende de `minio` healthy) — se probó vía `TestClient` con S3 mockeado (`moto`) en su lugar.
- `tests/integration/` sigue sin pruebas automatizadas formales; la integración real de este bloque se verificó manualmente (ver arriba), no quedó como test de pytest reproducible.
- Sprint 1 (S1) implementa los validadores reales (contable, RAG, LLM) que hoy el `worker` no ejecuta.
