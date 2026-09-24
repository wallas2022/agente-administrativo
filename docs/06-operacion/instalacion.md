# Instalación

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** docs/03-diseno/despliegue/estrategia-ambientes.md, docs/06-operacion/despliegue-stage-proxmox.md, infra/scripts/

Este documento cubre la instalación del ambiente **local** (desarrollo). Para **stage**, ver la guía dedicada — no se duplica aquí: [docs/06-operacion/despliegue-stage-proxmox.md](despliegue-stage-proxmox.md).

## Ambiente local (WSL2 + Docker Desktop)

### Requisitos

- Windows con WSL2 habilitado.
- Docker Desktop (con el backend de WSL2 activado).
- PC de referencia: Intel Core Ultra 7, 128 GB RAM, SSD, sin GPU dedicada (ver docs/03-diseno/despliegue/estrategia-ambientes.md §4).
- ~200 GB libres (modelos LLM + volúmenes de datos).
- Git.

### Pasos

1. **Configurar WSL2** — crear/editar `%UserProfile%\.wslconfig`:
   ```ini
   [wsl2]
   memory=96GB
   processors=<núcleos - 2>
   swap=16GB
   ```
   Reiniciar WSL2 (`wsl --shutdown`) para que tome efecto.

2. **Clonar el repositorio** dentro de WSL2 (recomendado, mejor rendimiento de E/S que `/mnt/c/...`).

3. **Copiar y completar variables de entorno**:
   ```bash
   cp .env.local.example .env.local
   ```
   Editar `.env.local` — no requiere secretos reales para desarrollo local (ver comentarios del archivo).

4. **Levantar los servicios**:
   ```bash
   ./infra/scripts/levantar-local.sh
   ```
   Equivalente a `docker compose --env-file .env.local -f infra/compose.yml -f infra/compose.local.yml up -d`. Agregar `--profile observabilidad` para incluir Prometheus, Grafana y Langfuse.

5. **Descargar el modelo LLM local** (dentro del contenedor `ollama` o desde el host apuntando a `http://localhost:11434`):
   ```bash
   docker compose -f infra/compose.yml -f infra/compose.local.yml exec ollama ollama pull gpt-oss:20b
   ```
   Ver `LLM_MODEL_PRINCIPAL` en `.env.local` para el modelo configurado (usado por el análisis, RF-04).

6. **Verificar** que los servicios están sanos:
   ```bash
   docker compose -f infra/compose.yml -f infra/compose.local.yml ps
   ```
   Todos los contenedores con healthcheck deben mostrar `healthy`.

7. **Acceder** a la aplicación en `https://localhost` (o el puerto configurado del proxy — certificado autofirmado en local, ver estrategia-ambientes.md §3).

### Detener el ambiente

```bash
docker compose -f infra/compose.yml -f infra/compose.local.yml down
```
Agregar `-v` para además eliminar los volúmenes (datos locales; irreversible).

## Ambiente stage

Ver [docs/06-operacion/despliegue-stage-proxmox.md](despliegue-stage-proxmox.md) — instalación del servidor físico, Proxmox VE, la VM `agente-stage`, el paquete offline y la configuración de `.env.stage`.

## Solución de problemas comunes

| Síntoma | Causa probable | Acción |
| --- | --- | --- |
| `ollama` no arranca / muy lento | RAM insuficiente asignada a WSL2 | Revisar `.wslconfig` (paso 1) |
| `docker compose config` falla pidiendo `.env.local` | El archivo no existe | Copiar desde `.env.local.example` (paso 3) |
| Puertos ocupados | Otro servicio usa el mismo puerto en el host | Ajustar el mapeo en `infra/compose.local.yml` |

## Pendientes

- [POR CONFIRMAR] Modelo de CPU exacto de la PC de desarrollo (afecta el número de `processors` en `.wslconfig`).
