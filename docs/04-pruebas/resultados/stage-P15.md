# Resultados — P-15 (Aprobación de fuentes y Garage en stage)

**Versión:** 0.1.0
**Fecha:** 2026-10-13
**Relacionado con:** docs/05-prompts/P-15-aprobacion-fuentes-y-garage.md, ADR-006 v2, ADR-010

## Bloque 1 — Errores visibles

| Ruta | Cambio | Pruebas |
| --- | --- | --- |
| `src/comun/almacenamiento.py` | `ObjetoNoEncontradoError`; `descargar_objeto` la lanza cuando el objeto no existe (NoSuchKey/404) | ok |
| `src/api/main.py` | Manejadores: objeto ausente → 409 con "El archivo de la fuente no está en el almacenamiento; súbalo de nuevo"; `httpx.TimeoutException` → 504; cualquier otra excepción → 500 JSON `{error, detalle}` con cabeceras CORS (solo para orígenes permitidos) y sin filtrar el mensaje interno (se registra con traza) | ok |
| `src/ui/src/utils/errores.ts` | `mensajeDeError` (lee `detalle`/`detail`/422) y `MENSAJE_SIN_CONEXION` | ok |
| `src/ui/src/paginas/BaseConocimiento.tsx`, `Chat.tsx` | Aprobar, vista previa, subida de fuente/plantilla y chat muestran el mensaje del servidor en vez de textos genéricos; aprobar captura errores de red | ok |
| `tests/unit/test_errores_visibles.py`, `src/ui/src/utils/errores.test.ts` | 5 + 4 pruebas nuevas | ok |

Métricas: pytest 715 pasan (cobertura 94 %), mypy sin errores, vitest 127 pasan, tsc sin errores, oxlint solo advertencias preexistentes.

Nota: la respuesta incluye `detail` además de `detalle` para que la UI existente (que leía `detail`) siga funcionando.

## Bloque 2 — Fragmentación

| Ruta | Cambio | Pruebas |
| --- | --- | --- |
| `src/curaduria/extraccion.py` | Dentro de cada sección/página se divide por párrafos (luego oraciones y, en último caso, palabras) con tope `FRAGMENTO_MAX_TOKENS`=450 y solapamiento `FRAGMENTO_SOLAPE_TOKENS`=60, ambos configurables por variable de entorno. Un cambio de página en PDF abre un fragmento nuevo con su `pagina` y conserva la `seccion`. Se limpian líneas de índice con puntos guía, encabezados/pies repetidos (texto corto en 3 o más páginas, ignorando números) y caracteres de control. | ok |
| `tests/unit/test_curaduria_fragmentacion.py` | 13 pruebas: tope, solapamiento, sin pérdida de contenido, párrafo gigante, palabra sin espacios, configuración por entorno, páginas, limpieza y PDF de 300 páginas. | ok |

- `fuente_id` y `version` los agrega `indexar_fuente` al payload de cada fragmento; `seccion` y `pagina` se conservan desde la extracción. El contenido que va a embeddings es exactamente `fragmento.contenido`, ya acotado.
- Los tokens se estiman a ~3 caracteres por token, sin tokenizador (conservador, sobrestima el español con bge-m3). [POR CONFIRMAR] contra el tokenizador real de bge-m3 en stage.
- Métricas: pytest 728 pasan (cobertura 94 %), mypy sin errores.

## Bloque 3 — Aprobación asíncrona

| Ruta | Cambio | Pruebas |
| --- | --- | --- |
| `src/curaduria/aprobacion.py` (nuevo) | `iniciar_indexacion` (borrador/error_indexacion → indexando) y `procesar_indexacion` (extrae, embebe, indexa; al final vigente con la versión anterior obsoleta en la misma transacción, o `error_indexacion` con motivo). Progreso "N de M" confirmado fragmento a fragmento. Bitácora en cada transición. Reintento idempotente. | ok (8) |
| `src/curaduria/indexacion.py` | `indexar_fragmentos` acepta `estado_payload`, `exigir_vigente` y `al_progresar` (el comportamiento por defecto no cambia). | ok |
| `src/comun/modelos.py`, migración `d41a9b7c5e20` | Columnas `fragmentos_total`, `fragmentos_procesados`, `motivo_error` en `fuente_conocimiento`. | ok |
| `src/comun/cola.py`, `src/orquestador/orquestador/tareas.py` | Tarea `indexar_fuente_conocimiento` en la cola `indexacion`; el registro de uso de P-13 (`embeddings_kb`) se conserva. | ok (mypy) |
| `src/api/main.py`, `esquemas.py` | `POST /curaduria/fuentes/{id}/aprobar` responde 202 `{estado: "indexando"}`; también sirve para reintentar desde `error_indexacion`. 409 si ya indexa; 503 y `error_indexacion` si la cola no responde; 409 si el archivo no está en el almacenamiento. El listado expone progreso y motivo. | ok (+3 pruebas de API) |
| `src/orquestador/Dockerfile`, `infra/compose*.yml` | La imagen del worker incluye `curaduria`; servicio `worker_indexacion` (`-Q indexacion -c 1`). `docker compose config` válido. | ok |
| `src/ui/.../BaseConocimiento.tsx` y `.css`, `esquema.ts` | Estado con "indexando: fragmento N de M", sondeo cada 3 s mientras haya fuentes indexando, motivo de error y botón Reintentar. | ok (+4 pruebas) |

- Riesgo evaluado antes de implementar: CU-01, CU-05 y el chat leen Qdrant con `estado == "vigente"`, así que no se ven afectados. La versión anterior sigue buscable mientras la nueva indexa.
- Pendiente en stage: reconstruir la imagen del worker, aplicar `alembic upgrade head` y levantar `worker_indexacion`.
- Métricas: pytest 739 pasan (cobertura 94 %), mypy y ruff sin errores, vitest 131 pasan, tsc sin errores.

## Bloque 4 — Embeddings robustos

| Ruta | Cambio | Pruebas |
| --- | --- | --- |
| `src/rag/cliente_embeddings.py` | `EMBEDDINGS_TIMEOUT_S` (300 por defecto) reemplaza el 30.0 fijo. Nuevo `obtener_embeddings_lote_con_metricas` con `input` como lista en `/api/embed` (`EMBEDDINGS_LOTE`=16). 3 reintentos (`EMBEDDINGS_REINTENTOS`) con espera creciente 2, 4, 8 s ante timeout, error de conexión o 5xx; un 4xx no se reintenta. `EMBEDDINGS_KEEP_ALIVE` (cae a `OLLAMA_KEEP_ALIVE`, luego 24h). Valida que el número de vectores coincida con el de textos. | ok (+11) |
| `src/comun/uso_llm.py` | `envolver_funcion_embedding_lote`: una fila de `uso_llm` por lote (tokens del lote completo; el error también queda registrado). `envolver_obtener_embedding` ya no fija 30 s. | ok (+2) |
| `src/curaduria/indexacion.py`, `aprobacion.py`, `tareas.py` | La indexación embebe por lotes; el worker pasa la función por lote con registro de uso. La ruta por texto se conserva para los demás llamadores. | ok (+1) |
| Búsqueda del chat y CU-01 | Heredan el timeout configurable porque `obtener_embedding` ya no tiene 30 s fijos. | ok (suite) |
| `.env*.example`, `configuracion-env-stage.md` | Variables `EMBEDDINGS_*` documentadas. | n/a |

- Con los valores por defecto, el peor caso de un lote que no responde es 4 intentos de 300 s más 14 s de esperas. Se puede acotar con `EMBEDDINGS_TIMEOUT_S` y `EMBEDDINGS_REINTENTOS`.
- El tiempo por lote en stage queda [POR CONFIRMAR]: se mide en el Bloque 6 con CONT-006 y CONT-007.
- Métricas: pytest 752 pasan (cobertura 94 %), mypy y ruff sin errores.

## Bloque 5 — Infraestructura

| Ruta | Cambio | Pruebas |
| --- | --- | --- |
| `infra/compose.stage.yml` | Servicio `garage` (`dxflrs/garage:v1.0.1`, binds `/srv/agente/garage/{meta,data}`, `garage.toml` de solo lectura, `red_interna`, sin puertos, 0.5 CPU y 512M). `localstack` queda con el perfil `solo-local`, así que no se levanta en stage. La `api` de stage depende de `garage` (`depends_on: !override`). | ok |
| `infra/garage/garage.toml.example` | Plantilla con `replication_factor = 1`, `s3_region = "us-east-1"` y `rpc_secret` de relleno (`openssl rand -hex 32`). | ok |
| `infra/scripts/inicializar-garage.sh` | Idempotente: layout (solo si el nodo no tiene rol), llave `agente-app` (se imprime solo al crearla o con `--mostrar-credenciales`) y buckets `conocimiento` y `documentos` con permisos. | ok (sintaxis `bash -n`); [POR CONFIRMAR] ejecución real en stage |
| `.env.stage.example`, `.gitignore` | `MINIO_ENDPOINT=garage:3900`; `infra/garage/garage.toml` ignorado por Git. | ok |
| `src/api/requirements.txt` | `alembic==1.14.0` ya estaba (una sola línea); queda cubierto por una prueba. | ok |
| Límites de memoria | `ollama` 64G → 44G (VM de 60 GB) y `proxy` 64G → 256M. Quedan [POR CONFIRMAR] con `docker stats` bajo carga. | ok |
| `tests/unit/test_infra_stage.py` (nuevo) | 13 pruebas sobre la configuración renderizada de Compose (stage y local), la plantilla, el script, `.gitignore` y la ausencia de `rpc_secret` reales en el repositorio. | ok |
| `docs/06-operacion` | Pasos de `garage.toml`, inicialización de Garage, `worker_indexacion` y límites de memoria. | n/a |

- No se pudo ejecutar Garage en esta máquina (el servicio de Docker no está activo); el script se validó estáticamente y debe probarse en stage. La suma de límites de memoria de los servicios (≈ 67 GB) supera los 60 GB de la VM, pero son límites y no reservas.
- El `docker-compose` local no cambia: LocalStack sigue siendo su almacenamiento y la prueba lo verifica.
- Métricas: pytest 765 pasan (cobertura 94 %), mypy y ruff sin errores.
