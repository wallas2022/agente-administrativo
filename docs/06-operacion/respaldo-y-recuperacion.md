# Respaldo y recuperación

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** RNF-07, RNF-12, docs/04-pruebas/casos-prueba/PP-15.md, docs/04-pruebas/casos-prueba/PP-19.md, infra/proxmox/vm-spec.md

## Objetivos

| Métrica | Valor |
| --- | --- |
| RPO (Recovery Point Objective) | 24 horas |
| RTO (Recovery Time Objective) | 4 horas |
| Retención de documentos y resultados | 90 días (3 meses), eliminación automática y auditada (RNF-12, RN-08) |
| Retención de la bitácora de auditoría | [POR CONFIRMAR] (SRS §17.5) |

Solo aplica al ambiente **stage** (el ambiente local es descartable y reproducible; no requiere respaldo formal).

## Niveles de respaldo

### 1. Nivel VM (Proxmox Backup Server)

- Snapshot diario de la VM `agente-stage` completa, incluidos todos los volúmenes de Docker.
- Retenido en almacenamiento externo (fuera del servidor físico) — ver infra/proxmox/vm-spec.md.
- Se toma también un snapshot manual **antes de cada despliegue** (rollback inmediato ante una versión fallida, ver docs/06-operacion/despliegue-stage-proxmox.md §9).

### 2. Nivel aplicación (volcado de datos)

| Servicio | Método | Frecuencia |
| --- | --- | --- |
| PostgreSQL | `pg_dump` completo | Diario |
| MinIO | Sincronización del bucket `documentos` a almacenamiento de respaldo | Diario |
| Qdrant | Snapshot de la colección `agente_admin_kb` | Diario |

El volcado de aplicación complementa (no reemplaza) el snapshot de VM: permite restaurar solo los datos sin reconstruir toda la VM.

## Procedimiento de restauración

1. Detener los servicios: `docker compose --env-file .env.stage -f compose.yml -f compose.stage.yml down`.
2. Elegir el punto de restauración:
   - Falla de la VM completa → restaurar snapshot de Proxmox Backup Server.
   - Corrupción de datos únicamente → restaurar el volcado más reciente de PostgreSQL/MinIO/Qdrant sobre una VM sana.
3. Restaurar los datos (`pg_restore`, copia de objetos MinIO, carga de snapshot Qdrant según corresponda).
4. Levantar los servicios: `docker compose --env-file .env.stage -f compose.yml -f compose.stage.yml up -d`.
5. Ejecutar las pruebas de humo (ver docs/06-operacion/despliegue-stage-proxmox.md §7).
6. Registrar el incidente y el tiempo real de recuperación.

## Depuración por retención (RN-08, RNF-12)

Un job periódico revisa `documento.fecha_expiracion` (90 días desde la carga) y elimina automáticamente los documentos y versiones vencidos de MinIO y PostgreSQL, registrando cada eliminación en la bitácora (ver docs/03-diseno/flujos/pipeline-validacion.md, subgrafo RETENCION). Esto **no es un respaldo**: es la política de retención de datos operativos, verificada en PP-19.

## Pruebas

- **PP-15** (docs/04-pruebas/casos-prueba/PP-15.md): restauración completa desde respaldo, medida contra el RTO de 4 h. Prueba de restauración sugerida con frecuencia trimestral.
- **PP-19** (docs/04-pruebas/casos-prueba/PP-19.md): verificación de la depuración automática por retención.

## Pendientes

- [POR CONFIRMAR] Retención exacta de la bitácora de auditoría (distinta de los 90 días de documentos).
- [POR CONFIRMAR] Ubicación física/lógica del almacenamiento externo de Proxmox Backup Server.
- [POR CONFIRMAR] Automatización real del job de retención (frecuencia, alertas si falla).
