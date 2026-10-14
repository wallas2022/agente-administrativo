#!/usr/bin/env bash
# Inicializa Garage en STAGE de forma idempotente: layout del nodo, llave de acceso
# y buckets `conocimiento` y `documentos`. Se puede ejecutar varias veces sin efectos
# colaterales. Relacionado con: ADR-006 v2, infra/garage/garage.toml.example
#
# Uso (en la VM stage, con el servicio garage ya levantado):
#   infra/scripts/inicializar-garage.sh                          # no imprime secretos
#   infra/scripts/inicializar-garage.sh --mostrar-credenciales   # imprime la llave
#
# La llave solo se imprime al crearla o con --mostrar-credenciales; cópiela a
# MINIO_ACCESS_KEY / MINIO_SECRET_KEY de .env.stage (nunca a Git).
set -euo pipefail

cd "$(dirname "$0")/.."   # -> infra/

ENV_FILE="${ENV_FILE:-../.env.stage}"
CAPACIDAD="${GARAGE_CAPACIDAD:-200G}"   # [POR CONFIRMAR] según el disco de /srv/agente/garage/data
ZONA="${GARAGE_ZONA:-dc1}"
LLAVE="${GARAGE_LLAVE:-agente-app}"
BUCKETS=(conocimiento documentos)
MOSTRAR=0
[ "${1:-}" = "--mostrar-credenciales" ] && MOSTRAR=1

COMPOSE=(docker compose --env-file "$ENV_FILE" -f compose.yml -f compose.stage.yml)

# La imagen de Garage solo trae el binario /garage (sin shell).
garage() { "${COMPOSE[@]}" exec -T garage /garage "$@"; }

echo "Esperando a que Garage responda..."
for _ in $(seq 1 30); do
  garage status >/dev/null 2>&1 && break
  sleep 2
done
garage status >/dev/null

# 1. Layout: asignar el nodo solo si todavía no tiene rol.
if garage status | grep -q "NO ROLE ASSIGNED"; then
  nodo="$(garage node id -q | cut -d@ -f1)"
  garage layout assign -z "$ZONA" -c "$CAPACIDAD" "$nodo"
  version="$(garage layout show | sed -n 's/.*layout version: *\([0-9][0-9]*\).*/\1/p' | head -n 1)"
  garage layout apply --version "$(( ${version:-0} + 1 ))"
  echo "Layout aplicado (zona $ZONA, capacidad $CAPACIDAD)."
else
  echo "Layout ya aplicado."
fi

# 2. Llave de acceso de la aplicación.
if ! garage key info "$LLAVE" >/dev/null 2>&1; then
  echo "Llave '$LLAVE' creada. Guarde estas credenciales en .env.stage ahora (no se vuelven a mostrar):"
  garage key create "$LLAVE"
else
  echo "Llave '$LLAVE' ya existe."
  if [ "$MOSTRAR" -eq 1 ]; then
    garage key info "$LLAVE" --show-secret
  fi
fi

# 3. Buckets y permisos (allow es idempotente).
for bucket in "${BUCKETS[@]}"; do
  if ! garage bucket info "$bucket" >/dev/null 2>&1; then
    garage bucket create "$bucket"
    echo "Bucket '$bucket' creado."
  else
    echo "Bucket '$bucket' ya existe."
  fi
  garage bucket allow --read --write --owner "$bucket" --key "$LLAVE"
done

echo "Garage listo: buckets ${BUCKETS[*]} con acceso para la llave '$LLAVE'."
