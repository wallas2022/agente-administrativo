# infra/scripts/

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** docs/06-operacion/instalacion.md, docs/06-operacion/respaldo-y-recuperacion.md

Scripts operativos de la infraestructura (arranque por ambiente, empaquetado/carga offline, respaldo, restauración, verificación de salud). Sin lógica de negocio.

## Scripts disponibles

| Script | Propósito |
|---|---|
| `levantar-local.sh` | Levanta el ambiente local con `compose.yml` + `compose.local.yml`. Ver [docs/03-diseno/despliegue/estrategia-ambientes.md](../../docs/03-diseno/despliegue/estrategia-ambientes.md) §4. |
| `empaquetar-offline.sh vX.Y.Z` | Construye y empaqueta imágenes + modelos para transferir a stage sin internet. Ver [docs/06-operacion/despliegue-stage-proxmox.md](../../docs/06-operacion/despliegue-stage-proxmox.md) §5. |
| `cargar-en-stage.sh vX.Y.Z` | Carga el paquete offline y levanta el ambiente stage en la VM. Ver [docs/06-operacion/despliegue-stage-proxmox.md](../../docs/06-operacion/despliegue-stage-proxmox.md) §5-6. |

## Contenido previsto (F5)

- Script de respaldo de PostgreSQL, Qdrant y MinIO.
- Script de restauración (soporte a RPO/RTO definidos en [docs/06-operacion/respaldo-y-recuperacion.md](../../docs/06-operacion/respaldo-y-recuperacion.md)).
- Verificación de salud de servicios (`docker compose ps` + healthchecks).

Pendiente de implementación.
