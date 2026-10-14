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
