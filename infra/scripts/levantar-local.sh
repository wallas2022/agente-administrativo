#!/usr/bin/env bash
# Levanta el ambiente LOCAL (desarrollo): crea .env.local si falta, levanta los
# servicios, descarga los modelos configurados en ollama y espera a que todo
# quede healthy. Esqueleto operativo: sin lógica de negocio.
# Relacionado con: docs/03-diseno/despliegue/estrategia-ambientes.md §4
set -euo pipefail

cd "$(dirname "$0")/.."   # -> infra/

# Requisitos reales verificados en esta máquina de desarrollo (2026-09-24):
# Intel Core Ultra 7 255H, 16 núcleos, 30.9 GB RAM total (NO 128 GB, ver
# docs/04-pruebas/resultados/local-L1.md), 344 GB libres en disco.

if [ ! -f ../.env.local ]; then
  echo "No existe .env.local — copiando desde .env.local.example." >&2
  cp ../.env.local.example ../.env.local
  echo "Revisa/ajusta ../.env.local antes de continuar si lo necesitas." >&2
fi

# shellcheck disable=SC1091
set -a; source ../.env.local; set +a

echo "== Levantando servicios (compose.yml + compose.local.yml) ==" >&2
docker compose --env-file ../.env.local -f compose.yml -f compose.local.yml up -d "$@"

echo "== Esperando healthchecks ==" >&2
SERVICIOS_CORE="proxy api orquestador worker redis ollama qdrant postgres minio languagetool"
for intento in $(seq 1 60); do
  PENDIENTES=""
  for s in $SERVICIOS_CORE; do
    estado=$(docker compose -f compose.yml -f compose.local.yml ps --format json "$s" 2>/dev/null \
      | python3 -c "import json,sys; l=[json.loads(x) for x in sys.stdin if x.strip()]; print(l[0].get('Health','') if l else 'sin_iniciar')" 2>/dev/null || echo "sin_iniciar")
    if [ "$estado" != "healthy" ] && [ -n "$estado" ]; then
      PENDIENTES="$PENDIENTES $s($estado)"
    fi
  done
  if [ -z "$PENDIENTES" ]; then
    echo "Todos los servicios core están healthy." >&2
    break
  fi
  echo "  Pendientes: $PENDIENTES (intento $intento/60)" >&2
  sleep 5
done

echo "== Descargando modelos en ollama ==" >&2
echo "  Modelo principal: ${LLM_MODEL_PRINCIPAL:-[POR CONFIRMAR en .env.local]}" >&2
docker compose -f compose.yml -f compose.local.yml exec -T ollama ollama pull "${LLM_MODEL_PRINCIPAL:?LLM_MODEL_PRINCIPAL no definido en .env.local}"
echo "  Embeddings: ${LLM_MODEL_EMBEDDINGS:-bge-m3}" >&2
docker compose -f compose.yml -f compose.local.yml exec -T ollama ollama pull "${LLM_MODEL_EMBEDDINGS:-bge-m3}"

echo "== Listo. Ver docs/06-operacion/instalacion.md para el resto de la verificación. ==" >&2
