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

## Bloque 6 — Pruebas de cierre

| Prueba | Resultado |
| --- | --- |
| PDF de 300 páginas (una sola sección que las abarca): `POST /aprobar` responde 202 `indexando` solo encolando; el worker indexa en lotes de 16 | ok: 2,391 fragmentos, máximo estimado 450 tokens (tope), ninguno cerca del límite de 2,048 de Ollama, sin truncado. API: 16 ms. Worker: 3.5 s con embeddings falsos (la cifra real depende del Ollama de stage: [POR CONFIRMAR]). |
| `ReadTimeout` simulado en `httpx.post` de embeddings | ok: 1 intento y 2 reintentos, y la fuente queda en `error_indexacion` con "El servicio de embeddings tardó demasiado en responder…" visible en el listado. Sin fragmentos huérfanos. Bitácora `fuente_indexacion_fallida`. Al volver Ollama, el mismo endpoint (Reintentar) la deja `vigente` y la bitácora registra `fuente_indexacion_reintentada`. |
| Objeto ausente en el almacenamiento | ok: 409 con el mensaje al aprobar; si desaparece entre el encolado y el worker, queda `error_indexacion` con el mismo mensaje. |
| Mensaje en la UI (aprobar, error de indexación con Reintentar, sondeo del progreso) | ok (vitest, Bloques 1 y 3). |
| Regresión: la búsqueda (chat, CU-01) mientras se reindexa | ok: durante la indexación de la versión 2 la búsqueda solo devuelve la versión 1; al terminar, solo la versión 2 (la 1 queda `obsoleta`). |
| Regresión CU-01, CU-05, chat y registro de uso P-13 | ok: suite completa. |
| Reindexar CONT-006 y CONT-007 | **Pendiente en stage**: son fuentes reales de stage y no existen en el repositorio ni en el ambiente local. Procedimiento abajo. |

Métricas: pytest 769 pasan (cobertura 94 %), mypy y ruff sin errores, vitest 131 pasan, tsc sin errores.

### Procedimiento para CONT-006 y CONT-007 (en stage)

> Guía detallada y completa del despliegue en stage (respaldo, Garage, migración, verificación y reindexado): [guia-despliegue-p15-stage.md](../../06-operacion/guia-despliegue-p15-stage.md).

1. Desplegar: `git pull`, `dcs build`, `alembic upgrade head` (migración `d41a9b7c5e20`), preparar `garage.toml`, `dcs up -d` e `infra/scripts/inicializar-garage.sh`; confirmar `worker_indexacion` arriba (`dcs ps`).
2. Si el archivo se perdió con LocalStack, la pantalla avisará "El archivo de la fuente no está en el almacenamiento; súbalo de nuevo": volver a subir el archivo.
3. Si la fuente quedó en `borrador` (el 500 anterior revirtió la transacción): pulsar **Aprobar**. Si quedó en `error_indexacion`: pulsar **Reintentar**.
4. Si alguna ya está `vigente` con fragmentos grandes: subir el mismo archivo como versión nueva del mismo `fuente_id` y aprobarla; la anterior pasa a `obsoleta` al terminar.
5. Seguimiento: el estado muestra "indexando: fragmento N de M"; `dcs logs -f worker_indexacion`; las filas `embeddings_kb` de `uso_llm` (una por lote) dan el tiempo real por lote en el dashboard de P-13.
6. Anotar aquí fragmentos, duración total y tiempo por lote medidos, y verificar con el chat que ambas fuentes responden con citas.

## Hallazgo local 14/10 — worker de indexación sin el paquete `curaduria`

Al probar P-15 en local, las fuentes aprobadas quedaron en `indexando` para siempre. En el log de `worker_indexacion`: `ModuleNotFoundError: No module named 'curaduria'`.

- **Causa:** Celery quita el directorio de trabajo de `sys.path` al terminar de cargar la app. La tarea importaba `curaduria` dentro de la función (en el momento de ejecutarse), y ese paquete no se había cargado al arrancar. Los demás paquetes (`rag`, `ocr`, `comun`) ya estaban cargados porque los pipelines los importan al inicio. En stage habría ocurrido igual.
- **Corrección (commit `f313d92`):** los imports van al inicio de `orquestador/tareas.py`, y ante cualquier falla inesperada la tarea marca la fuente como `error_indexacion` con el motivo en vez de dejarla en `indexando`.
- **Pruebas nuevas:** el módulo carga sus dependencias al importarse (en un proceso aparte), `marcar_error_indexacion`, y una falla inesperada de la tarea deja la fuente en `error_indexacion`.

## Bloque 3.5 — Unicidad de fuentes

Hallazgo local 14/10: dos fuentes distintas se crearon con `CONTIT-001` versión 1.

| Ruta | Cambio | Pruebas |
| --- | --- | --- |
| `src/curaduria/fuentes.py` | `evaluar_alta_fuente`: mismo ID y versión → 409 "Ya existe {id} versión {v}; use otro ID o suba una nueva versión"; mismo ID con otra versión → nueva versión solo si coinciden área y tipo (se advierte si el título difiere); ID de otra área → 403; tipo distinto → 409. | ok (17) |
| `src/api/main.py` | `POST /curaduria/fuentes` valida **antes de subir el archivo** (la llave del objeto incluye ID y versión, así que un duplicado habría sobrescrito el archivo existente); captura la carrera con la restricción de la base (409). Nuevo `POST /curaduria/fuentes/validar-alta` para la UI. | ok (+8) |
| `src/comun/modelos.py`, migración `e7b2c9a14f60` | `UNIQUE (fuente_id, version)`. La migración **se detiene y lista los duplicados sin borrar nada** si los hay. | ok |
| `src/curaduria/duplicados.py` | Listado de solo lectura (`python -m curaduria.duplicados`): id, título, tipo, estado, área, fecha y fragmentos de cada fila repetida. | ok |
| `src/curaduria/plantilla.py` | El importador (`validar` e `importar`) rechaza IDs ya existentes o de otra área con hoja, fila y columna; el ID repetido dentro de la hoja ya se rechazaba. | ok |
| `src/ui/.../BaseConocimiento.tsx` | Comprobación previa al escribir ID y versión (mensaje, advertencia y botón bloqueado) y de nuevo al enviar, antes de subir el archivo. | ok (+3) |

Métricas: pytest 798 pasan (cobertura 94 %), mypy y ruff sin errores, vitest 134 pasan, tsc sin errores.

## Hallazgos locales 15/10 — chat

Detectados al preparar las capturas de la presentación:

| Hallazgo | Causa | Corrección | Prueba |
| --- | --- | --- | --- |
| El chat respondía con un mensaje vacío (solo las fuentes) | gpt-oss gastó los 800 tokens permitidos razonando y no redactó texto; con fuentes antiguas de fragmentos grandes el contexto llegaba a ~2,050 tokens | Si la respuesta viene vacía se guarda un mensaje explicativo ("Reformule la pregunta…"). Pendiente de fondo: reindexar las fuentes grandes con la fragmentación de 450 tokens | `test_respuesta_vacia_del_modelo_se_reemplaza_por_un_mensaje_explicativo` |
| Mientras el chat esperaba a la IA, el servidor no atendía a nadie (ni el inicio de sesión) | `enviar_mensaje_chat` es `async` y llamaba a la IA de forma bloqueante (bloqueaba el ciclo de eventos) | Búsqueda, generación y lectura de adjuntos corren en un hilo (`run_in_threadpool`) | `test_mientras_el_chat_espera_a_la_ia_el_servidor_sigue_atendiendo_a_los_demas` |
| Las explicaciones y respuestas mostraban `**texto**` | La interfaz no interpretaba las negritas | Componente `TextoConNegritas` (sin HTML crudo) en hallazgos y chat | 2 pruebas de UI |

El segundo hallazgo afecta directamente a la capacidad con usuarios simultáneos: sin esta corrección, una sola pregunta al chat paraba la API para todos. Las pruebas de carga deben ejecutarse con la imagen que ya la incluye.

## Prueba de carga en stage 15–16/10: hallazgos y correcciones

Primera ronda de usuarios simultáneos (ver `tests/carga/README.md`).

| Escenario | Resultado | Causa y corrección |
| --- | --- | --- |
| Ortografía, 3 / 5 / 10 usuarios | 100 % sin fallos; total p90 de 9.5, 7.2 y 10.8 s | Medido. Nota: no incluye la validación de la IA de los casos dudosos, que sigue en segundo plano |
| Ortografía, 1 usuario | Falló a los 21 s con `timed out` | LanguageTool tenía un límite fijo de 20 s y la primera petición tras un rato sin uso es lenta. Ahora 60 s configurable (`LANGUAGETOOL_TIMEOUT_S`) |
| Excel contable, 1 / 3 / 5 usuarios | 0 de 9 completados, todos `timed out` a ~5:15–5:30 | **Ollama estaba recortado por Docker:** el contenedor tenía un límite de 16 CPU (puesto a mano en stage) con la VM en 20 vCPU y Ollama lanzando 20 hilos; el 97.8 % de los ciclos de CPU estaban pausados (`nr_throttled 62880` de `nr_periods 64276`, ~6 h de CPU pausada). El archivo del repositorio decía 8 CPU, que tampoco coincidía. Corregido a 20 CPU y 80G, igual que la VM |
| Excel contable tras recrear Ollama | Sigue fallando a ~5:15 (a confirmar si el contenedor se recreó con 20 CPU) | La llamada a la IA del análisis contable no tenía tope de razonamiento ni de salida y, si vencía, **todo el análisis se marcaba fallido** aunque las reglas ya hubieran terminado. Ahora: razonamiento bajo y salida acotada (2,500 tokens), `LLM_TIMEOUT_S` configurable y, si la IA no responde, los hallazgos se publican con el texto de respaldo (el uso queda registrado como timeout) |

Pendiente: medir de nuevo en stage con Ollama a 20 CPU y la imagen nueva del worker. La tabla de carga ahora incluye "Sin explicación IA" para distinguir un análisis completo de uno degradado.

## Velocidad real de la IA en stage (21/10)

Medida con 40 tokens, razonamiento bajo y la CPU de Ollama ya en 20 (VM de 20 vCPU sobre un servidor de 12 núcleos físicos, sin AVX; `st` = 0 en `vmstat`, es decir, el servidor físico no estaba sobrecargado):

| Hilos de Ollama | Generación (tokens/s) | Carga del modelo |
| --- | --- | --- |
| 10 o 6 (la salida se cortó al pegar) | 2.12 | 71.8 s (primera, con el modelo recién arrancado) |
| 12 | **2.32** | 15.2 s |
| 20 (valor por defecto = vCPU) | 1.33 | 14.5 s |

- **Lectura del prompt: ~3 tokens por segundo** (73 tokens en 22–25 s). En una CPU con AVX2 leer es decenas de veces más rápido que generar; aquí es igual de lento. Es el cuello de botella: un prompt de 1,500 tokens tarda unos 8 minutos solo en leerse, más que el límite de 300 s.
- **Por qué fallaba el análisis contable:** el prompt incluía hasta 3 fragmentos completos (~450 tokens cada uno) por hallazgo, más uno de referencia.
- **Cambiar el número de hilos recarga el modelo** (~15 s por cambio): el valor debe ser fijo en todas las llamadas.
- **Ollama arrancó con 4 espacios paralelos** (visto en el log) porque el `.env.stage` de stage tiene `OLLAMA_NUM_PARALLEL=4`. No es un error de entrega (corregido en una nota anterior de este mismo informe); queda pendiente medir si 1 o 4 conviene con la prueba de carga.

Correcciones: `LLM_NUM_THREAD=12`, prompt compacto (2 fragmentos de hasta 400 caracteres), `LLM_TIMEOUT_S=600` en stage. Con esta velocidad, cada análisis contable tardaría del orden de varios minutos (la lectura de ~450 tokens y la generación de ~150 tokens suman unos 3–4 minutos por llamada): válido para el piloto, pero la capacidad con muchos hallazgos o usuarios depende de la decisión de hardware (ADR-005) o de modelo.

