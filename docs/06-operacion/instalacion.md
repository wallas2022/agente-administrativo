# Instalación

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** docs/03-diseno/despliegue/estrategia-ambientes.md, docs/06-operacion/despliegue-stage-proxmox.md, infra/scripts/

Este documento cubre la instalación del ambiente **local** (desarrollo). Para **stage**, ver la guía dedicada — no se duplica aquí: [docs/06-operacion/despliegue-stage-proxmox.md](despliegue-stage-proxmox.md).

## Ambiente local (WSL2 + Docker Desktop)

### Requisitos

- Windows con WSL2 habilitado.
- Docker Desktop (con el backend de WSL2 activado).
- **Ollama nativo de Windows** ([ollama.com/download](https://ollama.com/download)) — el motor LLM real en local corre aquí, no en Docker (ver "Motor LLM" más abajo).
- PC de referencia usada para verificar este documento: Intel Core Ultra 7 255H, **30.9 GB RAM real** (el SRS v0.6 §7 dice 128 GB; esa cifra no coincidía con esta máquina — ver docs/04-pruebas/resultados/local-L1.md), SSD, sin GPU dedicada.
- ~50 GB libres (modelos LLM del Ollama nativo + volúmenes de datos de Docker; menos que lo estimado originalmente porque el LLM ya no vive dentro de Docker).
- Git.

### Motor LLM: nativo, no en Docker

En esta máquina, ejecutar el LLM dentro de Docker Desktop/WSL2 midió **~100 veces más lento** que Ollama nativo de Windows con el mismo modelo (0.06–0.08 tokens/s vs 7.0 tokens/s) — es un problema de la capa de virtualización, no del hardware ni de los límites de CPU/RAM del contenedor. Detalle completo en [docs/04-pruebas/resultados/local-L1.md](../04-pruebas/resultados/local-L1.md).

Por eso: instala Ollama nativo, descarga ahí los modelos, y `.env.local` apunta `LLM_BASE_URL` a `http://host.docker.internal:11434` (el puerto del Ollama nativo, alcanzable desde los contenedores). El `ollama` declarado en `infra/compose.local.yml` se deja corriendo sin modelos, solo por paridad de nombres de servicio con stage — no se usa para inferencia real en local.

### Pasos

1. **Configurar WSL2** — crear/editar `%UserProfile%\.wslconfig`. Con 30.9 GB de RAM real, no aplican los `memory=96GB` que asumía el SRS original; usar un valor acorde a la RAM real de tu máquina, dejando margen para Windows y Ollama nativo (que corre fuera de WSL2):
   ```ini
   [wsl2]
   memory=16GB
   processors=<núcleos - 2>
   swap=4GB
   ```
   Reiniciar WSL2 (`wsl --shutdown`) para que tome efecto. [POR CONFIRMAR] valor óptimo — ajustar según cuántos otros proyectos Docker corran a la vez en tu máquina.

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

5. **Descargar el modelo LLM en Ollama nativo** (no en el contenedor — ver "Motor LLM" arriba), desde una terminal normal de Windows:
   ```powershell
   ollama pull qwen2.5:14b
   ollama pull bge-m3
   ```
   Ver `LLM_MODEL_PRINCIPAL` / `LLM_MODEL_EMBEDDINGS` en `.env.local` para los modelos configurados (usados por el análisis, RF-04). El script `infra/scripts/levantar-local.sh` intenta hacer este paso automáticamente si `ollama` está en el `PATH`.

6. **Verificar** que los servicios están sanos:
   ```bash
   docker compose -f infra/compose.yml -f infra/compose.local.yml ps
   ```
   Todos los contenedores con healthcheck deben mostrar `healthy`.

7. **Acceder** a la aplicación en `https://localhost:8443` (puerto remapeado en esta máquina por conflicto con otro proyecto Docker que ya usaba el 443 — ver `infra/compose.local.yml`; certificado autofirmado en local, ver estrategia-ambientes.md §3).

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
| El análisis/redacción con LLM tarda minutos por token | Estás usando el `ollama` de Docker en vez del nativo | Verifica `LLM_BASE_URL=http://host.docker.internal:11434` en `.env.local`; ver docs/04-pruebas/resultados/local-L1.md |
| `docker compose config` falla pidiendo `.env.local` | El archivo no existe | Copiar desde `.env.local.example` (paso 3) |
| Puertos ocupados | Otro servicio usa el mismo puerto en el host | Ajustar el mapeo en `infra/compose.local.yml` |
| `minio` no descarga la imagen (`pull access denied`) | El repositorio `minio/minio` ya no permite pull anónimo en Docker Hub | Hacer `docker login` con una cuenta que tenga acceso, o resolver con otra imagen S3-compatible [POR CONFIRMAR] |

## Pendientes

- [POR CONFIRMAR] Modelo de CPU exacto de la PC de desarrollo de referencia de este documento (afecta el número de `processors` en `.wslconfig`) — el modelo de CPU en sí ya se confirmó (Intel Core Ultra 7 255H).
- [POR CONFIRMAR] Valor óptimo de `memory=` en `.wslconfig` dado que la RAM real (30.9 GB) es muy inferior a la que asumía el SRS original (128 GB).
