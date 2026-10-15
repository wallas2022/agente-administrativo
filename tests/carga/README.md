# Prueba de carga con usuarios simultáneos

**Versión:** 0.1.0 · **Fecha:** 2026-10-15
**Relacionado con:** PP-12, PP-13, RNF-04, RNF-05

`carga_concurrente.py` simula N usuarios que hacen lo mismo a la vez por la API (igual que la interfaz) y mide, por nivel de usuarios, los segundos hasta los primeros hallazgos, hasta terminar, los errores y los documentos por hora.

| Escenario | Qué hace cada usuario |
| --- | --- |
| `contable` | Sube el Excel de CU-01 (`tests/dataset/cu-01/cu01-08-multiples-errores.xlsx`, período 2026-01) y espera el análisis |
| `ortografia` | Sube un texto con errores (como el texto pegado de CU-05) y espera el análisis |
| `chat` | Hace una pregunta a la base de conocimiento |
| `mixto` | Reparte los tres anteriores entre los usuarios |

**Solo las cifras medidas en stage valen para RNF-04 y RNF-05.** En local son una referencia (otro hardware).

## Local (validar el script)

```bash
CARGA_PASSWORD='<contraseña>' .venv/Scripts/python.exe tests/carga/carga_concurrente.py \
  --base http://127.0.0.1:8001 --email analista@local \
  --escenario ortografia --usuarios 1,3 --md resultados.md
```

## Stage

Se ejecuta dentro de la red interna, desde un contenedor de la API (ya trae `httpx`) con la carpeta `tests/` montada. Use un usuario con permiso `analisis:crear` (rol Analista) y datos sintéticos. El Excel de prueba debe existir en `/opt/agente/app/tests/dataset/cu-01/`.

```bash
srv$ cd /opt/agente/app/infra
srv$ read -s CARGA_PASSWORD && export CARGA_PASSWORD      # no queda en el historial
srv$ dcs run --rm --no-deps -e CARGA_PASSWORD -v /opt/agente/app/tests:/tests api \
       python /tests/carga/carga_concurrente.py --base http://api:8000 \
       --email <analista> --escenario contable --usuarios 1,3,5,10 \
       --salida /tests/carga/resultados-stage-contable.json --md /tests/carga/resultados-stage-contable.md
```

Repita con `--escenario ortografia`, `--escenario chat` y `--escenario mixto`.

- **Un escenario a la vez** y, mientras corre, mire el Dashboard (pestaña Recursos): CPU y memoria de la VM, de `ollama` y de los workers.
- **Tiempo:** la IA atiende una petición a la vez (`OLLAMA_NUM_PARALLEL=1`), así que `contable` con 10 usuarios puede tardar casi una hora (el script espera hasta 30 minutos por análisis; cambie `--timeout-analisis-s` si hace falta). Empiece por `--usuarios 1,3` si quiere una primera lectura rápida.
- Los análisis generados quedan en el historial del usuario de prueba y se eliminan con la retención de 3 meses.
- Nunca ejecute esto con documentos reales ni contra producción.

## Cómo leer los resultados

- **Primeros hallazgos:** cuánto espera el usuario hasta ver algo (las reglas publican antes que la IA).
- **Total p50 / p90:** tiempo típico y del 90 % de los casos. Compárelos con el objetivo de RNF-04 (documento complejo en 10 minutos como máximo).
- **Docs/hora:** documentos terminados por hora con ese nivel de usuarios; contrástelo con la meta de unos 50 documentos al día (RNF-05).
- **Fallos:** cualquier fallo o tiempo excedido marca el límite de usuarios que la plataforma soporta hoy.
