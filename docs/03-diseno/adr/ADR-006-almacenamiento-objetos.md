# ADR-006 — Almacenamiento de objetos: LocalStack en local, pendiente en stage

**Versión:** 1.0
**Fecha:** 2026-09-25
**Relacionado con:** RF-03, RN-09, ADR-004, docs/03-diseno/c4/02-contenedores.md, docs/04-pruebas/resultados/local-localstack.md

## Estado

Aceptado para local. **Pendiente de decisión** para stage/producción.

## Contexto

El diseño original (SRS, C4, ADR-004) asumía **MinIO** como almacenamiento de objetos S3-compatible on-premise para documentos cargados (RF-03) y sus versiones corregidas. Al intentar levantar el ambiente local (2026-09-25) se confirmó que MinIO Inc. **descontinuó toda distribución gratuita** de su edición comunitaria:

| Vía intentada | Resultado |
| --- | --- |
| `docker pull minio/minio:*` (cualquier tag) | El repositorio ya no existe en Docker Hub (`404 object not found` en la API) |
| `docker pull bitnami/minio:latest` | Repositorio activo pero sin ningún tag público |
| `quay.io/minio/minio` | Exige autenticación incluso para leer metadatos |
| Binario nativo de Windows (`dl.min.io`, también vía `winget install MinIO.Server`) | `410 Gone`: "archived and no longer maintained... no longer served from this site" |

No es un problema de credenciales/token — MinIO simplemente ya no se puede obtener gratis por ninguna vía, ni como imagen Docker ni como binario. Esto invalida la elección de MinIO como backend de almacenamiento de objetos para cualquier ambiente, no solo local, y requiere una decisión de arquitectura nueva.

## Decisión

**Local (esta decisión, aceptada):** se usa **LocalStack** (solo el servicio S3, `SERVICES=s3`), que expone la misma API S3 que ya consumía `comun/almacenamiento.py` vía boto3 — sin cambios de lógica de negocio, solo de configuración de infraestructura (`infra/compose.yml`, `.env.local`). Verificado con carga multiparte real, descarga y flujo completo de CU-01 de punta a punta (ver docs/04-pruebas/resultados/local-localstack.md).

**Stage/producción (pendiente):** LocalStack es explícitamente una herramienta de simulación para desarrollo/pruebas, no un backend de almacenamiento durable pensado para producción (no tiene garantías de persistencia/replicación de nivel productivo en su edición comunitaria). Se proponen dos alternativas para evaluar cuando se resuelva ADR-005 (disponibilidad del servidor de stage):

| Alternativa | A favor | En contra |
| --- | --- | --- |
| **SeaweedFS** | Distribuido, gateway S3 nativo, imagen Docker pública activa (26M+ pulls), pensado para producción, soporta erasure coding y replicación. | Configuración inicial más compleja que un solo binario; menor familiaridad del equipo. |
| **Garage** | Binario/imagen simple, pensado específicamente para self-hosting a pequeña escala (encaja con el volumen del piloto), licencia AGPLv3 con desarrollo activo. | Proyecto más joven, comunidad más pequeña; menos probado a la escala de SeaweedFS. |

Ninguna de las dos se implementa todavía: **no se debe configurar stage** hasta que exista acceso al servidor físico (ADR-005) y se confirme cuál de las dos (u otra opción) se adopta formalmente, idealmente con una prueba de carga/durabilidad antes de comprometerse.

## Alternativas consideradas y descartadas

| Alternativa | Por qué se descarta |
| --- | --- |
| MinIO (imagen Docker o binario) | Ya no se distribuye gratis por ninguna vía verificada (ver tabla de contexto). |
| `bitnami/minio` | Repositorio activo pero sin tags públicos — inutilizable en la práctica. |
| `quay.io/minio/minio` | Requiere autenticación/cuenta adicional (Quay.io/Red Hat), fuera del alcance de "sin salida a internet en stage" (RNF-01) y sin garantía de que la cuenta gratuita permita descargar la imagen igualmente. |
| Usar LocalStack también en stage | Es una herramienta de simulación para desarrollo, no un backend de almacenamiento durable de producción; se descarta para stage aunque sea aceptable en local. |

## Consecuencias

- `infra/compose.yml`: servicio `minio` renombrado a `localstack` (imagen `localstack/localstack:4.9.1`, healthcheck vía `/_localstack/health`).
- Las variables de entorno mantienen el prefijo `MINIO_*` a propósito (`MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, etc.) para no dispersar el cambio por todo el código/documentación mientras no haya una decisión definitiva para stage; se revisará el nombre cuando se resuelva esta ADR para stage.
- `infra/compose.stage.yml` **sigue referenciando MinIO sin modificar** — no se toca hasta que se decida su reemplazo real, para no adelantar trabajo sobre una decisión de arquitectura todavía abierta.
- Documentación de respaldo (`infra/proxmox/vm-spec.md`, `infra/scripts/README.md`) sigue mencionando MinIO; debe actualizarse en el mismo momento en que se cierre esta decisión para stage.
- Pendiente explícito: abrir un ADR-006 v2 (o actualizar este) en cuanto exista acceso al servidor de stage, con la elección final entre SeaweedFS y Garage (o una tercera opción) y su justificación basada en pruebas reales.
