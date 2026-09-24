#!/usr/bin/env bash
# Empaqueta imágenes Docker y modelos Ollama para transferir a la VM stage sin
# internet (RNF-01). Ejecutar en la máquina de construcción (local o puente con
# internet), no en la VM stage. Esqueleto: sin lógica de negocio.
# Relacionado con: docs/06-operacion/despliegue-stage-proxmox.md §5
set -euo pipefail

cd "$(dirname "$0")/.."   # -> infra/

VERSION="${1:?Uso: empaquetar-offline.sh vX.Y.Z}"

# [POR CONFIRMAR] ruta real de modelos Ollama descargados en la máquina de construcción
OLLAMA_MODELS_DIR="${OLLAMA_MODELS_DIR:-$HOME/.ollama}"

docker compose -f compose.yml -f compose.stage.yml build

docker save "$(docker compose -f compose.yml -f compose.stage.yml config --images)" \
  | gzip > "agente-${VERSION}-imagenes.tar.gz"

tar czf "agente-${VERSION}-modelos.tar.gz" -C "${OLLAMA_MODELS_DIR}" models

sha256sum "agente-${VERSION}-imagenes.tar.gz" "agente-${VERSION}-modelos.tar.gz" > SHA256SUMS

echo "Paquete generado en infra/: agente-${VERSION}-imagenes.tar.gz, agente-${VERSION}-modelos.tar.gz, SHA256SUMS"
echo "Transferir los 3 archivos a la VM stage por la red interna y ejecutar cargar-en-stage.sh"
