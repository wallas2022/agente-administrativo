#!/usr/bin/env bash
# Levanta el ambiente LOCAL (desarrollo). Esqueleto: delega en docker compose, sin
# lógica de negocio. Relacionado con: docs/03-diseno/despliegue/estrategia-ambientes.md §4
set -euo pipefail

cd "$(dirname "$0")/.."   # -> infra/

# [POR CONFIRMAR] requisitos mínimos sugeridos: 16 GB RAM (32 GB recomendado),
# 8 núcleos, 100 GB libres, WSL2 habilitado (ver estrategia-ambientes.md §4).

if [ ! -f ../.env.local ]; then
  echo "Falta .env.local — copiar .env.local.example a .env.local y completar valores." >&2
  exit 1
fi

# Agregar --profile observabilidad para incluir también Prometheus y Grafana.
docker compose --env-file ../.env.local -f compose.yml -f compose.local.yml up -d "$@"
