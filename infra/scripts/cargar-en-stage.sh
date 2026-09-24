#!/usr/bin/env bash
# Carga el paquete offline (imágenes + modelos) y levanta el ambiente STAGE.
# Ejecutar en la VM stage, con los 3 archivos generados por empaquetar-offline.sh
# ya transferidos a infra/ por la red interna. Esqueleto: sin lógica de negocio.
# Relacionado con: docs/06-operacion/despliegue-stage-proxmox.md §5-6
set -euo pipefail

cd "$(dirname "$0")/.."   # -> infra/

VERSION="${1:?Uso: cargar-en-stage.sh vX.Y.Z}"

sha256sum -c SHA256SUMS

gunzip -c "agente-${VERSION}-imagenes.tar.gz" | docker load

# [POR CONFIRMAR] /srv/agente/ debe existir y pertenecer al usuario de servicio "agente"
tar xzf "agente-${VERSION}-modelos.tar.gz" -C /srv/agente/ollama/

if [ ! -f ../.env.stage ]; then
  echo "Falta .env.stage — copiar .env.stage.example a .env.stage con los secretos entregados por canal seguro." >&2
  exit 1
fi

docker compose --env-file ../.env.stage -f compose.yml -f compose.stage.yml up -d

echo "Ambiente stage levantado. Ejecutar pruebas de humo: docs/06-operacion/despliegue-stage-proxmox.md §7"
