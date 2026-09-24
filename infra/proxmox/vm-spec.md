# Especificación de VM — Proxmox VE

**Versión:** 0.3.0
**Fecha:** 2026-09-24
**Relacionado con:** [docs/03-diseno/despliegue/estrategia-ambientes.md](../../docs/03-diseno/despliegue/estrategia-ambientes.md), RNF (ver docs/01-requerimientos/01-requerimiento-formal.md)

## Host físico

| Recurso | Valor |
|---|---|
| Hipervisor | Proxmox VE |
| CPU | 2 (físicas/asignadas al host) — [POR CONFIRMAR] núcleos/hilos exactos |
| RAM | 384–512 GB |
| Disco | 4 TB |
| GPU | Sin GPU confirmada |

## VM propuesta (aplicación)

| Recurso | Valor |
|---|---|
| Cantidad de VMs | 1 |
| SO | Ubuntu 24.04 LTS |
| Runtime | Docker + Docker Compose |
| Tipo de CPU (Proxmox) | `host` (passthrough de instrucciones del CPU físico, requerido para rendimiento óptimo de inferencia en CPU) |
| Topología | NUMA habilitado, 2 sockets |
| RAM asignada | 256–320 GB, **fija, sin ballooning** (memoria reservada, no compartida dinámicamente) |
| Disco asignado | 2–2.5 TB (SSD si el host lo tiene disponible; de lo contrario el disco más rápido disponible) |
| Resto de recursos del host | Reservado para Proxmox VE (hipervisor, overhead de gestión, futuras VMs/snapshots) |
| Red | [POR CONFIRMAR] (VLAN, acceso a AD/LDAP) |

## PC de desarrollo (ambiente local)

No es Proxmox, pero se documenta aquí como referencia de dimensionamiento del ambiente local (ver [docs/03-diseno/despliegue/estrategia-ambientes.md](../../docs/03-diseno/despliegue/estrategia-ambientes.md) §4).

| Recurso | Valor |
|---|---|
| Equipo | PC del desarrollador, Windows |
| CPU | Intel Core Ultra 7 |
| RAM | 128 GB |
| Disco | SSD |
| GPU | Sin GPU dedicada (GPU integrada Intel Arc y NPU no se usan para inferencia) |
| Virtualización | WSL2 + Docker Desktop |
| Configuración WSL2 | `%UserProfile%\.wslconfig`: `memory=96GB`, `processors=<núcleos − 2>`, `swap=16GB` |

## Respaldos

Los respaldos de la VM se realizan con **Proxmox Backup Server** (backup a nivel de VM, incremental, con deduplicación), complementados por los respaldos a nivel de aplicación descritos en [docs/06-operacion/respaldo-y-recuperacion.md](../../docs/06-operacion/respaldo-y-recuperacion.md) (PostgreSQL, Qdrant, MinIO).

## Supuestos

1. Toda la carga de inferencia LLM corre en CPU (sin GPU confirmada); ver [docs/03-diseno/adr/ADR-001-motor-llm-cpu.md](../../docs/03-diseno/adr/ADR-001-motor-llm-cpu.md).
2. Una sola VM aloja todos los contenedores del stack en el prototipo; separación en múltiples VMs es una evolución futura [POR CONFIRMAR].
3. RAM fija (sin ballooning) se prioriza sobre RAM dinámica porque la inferencia en CPU necesita memoria predecible y contigua.
4. El rango 256–320 GB de RAM y 2–2.5 TB de disco deja margen del host (384–512 GB RAM / 4 TB disco) para Proxmox VE y crecimiento futuro; el valor exacto dentro de cada rango queda [POR CONFIRMAR] según carga real observada.
5. Existe una instancia de Proxmox Backup Server disponible o planificada para el respaldo de la VM [POR CONFIRMAR].
