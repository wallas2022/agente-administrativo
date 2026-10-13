# P-15 · Aprobación de fuentes y formalización de cambios de stage

Versión 1.0 · 2026-10-13 · Ejecutor: Claude Code · Depende de: CU-08 (Base de Conocimiento), P-13 (registro de uso del LLM), P-14 (chat) · Relacionado: ADR-005, ADR-006 v2, ADR-010

## 1. Tarea

Corregir la aprobación de fuentes y formalizar en el repositorio los cambios de stage del 2026-10-13. Detenerse al final de cada bloque y esperar visto bueno.

## 2. Evidencia de stage (lab-ia-01, CPU x86-64-v2 sin AVX, 8 vCPU, 60 GB)

1. `POST /curaduria/fuentes/{id}/aprobar` → 500; la UI queda en "Aprobando…" y el navegador lo reporta como CORS (el 500 sale sin cabeceras).
2. Traza: `api/main.py:2460 aprobar_fuente_endpoint` → `curaduria/indexacion.py:167 indexar_fuente` → `:95 funcion_embedding` por fragmento → `rag/cliente_embeddings.py:60 httpx.ReadTimeout` (timeout fijo 30.0 s en líneas 47 y 80).
3. `curaduria/extraccion.py extraer_fragmentos` corta por sección/página sin tope: fragmentos de 4,089 tokens → Ollama "input too large (batch 2048)", truncado a 2,048; un embedding de prueba tardó 173.8 s con Ollama ocupado (`OLLAMA_NUM_PARALLEL=1`).
4. `api/main.py:2424` y `:2370` → `comun/almacenamiento.py:108 descargar_objeto` falla cuando el objeto no existe.
5. LocalStack perdió objetos al reiniciar pese a `PERSISTENCE=1`. En stage se migró a Garage v1.0.1 (`dxflrs/garage`), probado: persistencia tras reinicio y carga multiparte de 1 GB OK. Hoy vive en `infra/compose.garage.yml` no versionado. `comun/almacenamiento.py` ya usa s3v4, `addressing_style=path` y región `us-east-1` (Garage con `s3_region=us-east-1`); botocore 1.35.99.
6. `alembic` no estaba en `src/api/requirements.txt` (solo en `requirements-dev.txt`); en stage se agregó a mano `alembic==1.14.0`.

No romper CU-01, CU-02, CU-05, chat_kb ni el registro de uso de P-13.

## 3. Documentación previa al bloque 1

ADR-006 v2 (decisión Garage para stage con la evidencia del punto 5; SeaweedFS queda como alternativa si se escala a varios nodos) y ADR-010 "Indexación asíncrona y fragmentación de fuentes". Actualizar `docs/06-operacion` (traslado-stage, configuracion-env-stage: Garage, permisos de `/srv/agente` para Prometheus uid 65534 y Grafana uid 472) y estado-proyecto. Solo Mermaid.

## 4. Bloques

### Bloque 1 · Errores visibles
Manejador global de excepciones: respuesta JSON `{error, detalle}` con cabeceras CORS también en 500. Objeto ausente en S3 → 409 "El archivo de la fuente no está en el almacenamiento; súbalo de nuevo". UI: mostrar el mensaje en aprobar, vista previa y chat en lugar de "Aprobando…" o "No se pudo conectar".

### Bloque 2 · Fragmentación
En `curaduria/extraccion.py`: dentro de cada sección/página, dividir por párrafos con tope `FRAGMENTO_MAX_TOKENS=450` y solapamiento `FRAGMENTO_SOLAPE_TOKENS=60` (configurables). Conservar `fuente_id`, `version`, `seccion` y `pagina`. Limpiar líneas de índice con puntos guía, encabezados/pies repetidos y caracteres de control. Nunca enviar a embeddings más del tope.

### Bloque 3 · Aprobación asíncrona
Aprobar responde de inmediato: estado "indexando" y tarea Celery en el worker. Al terminar: "vigente" (la versión anterior pasa a obsoleta en la misma transacción); si falla: "error_indexacion" con motivo, visible en la UI con botón Reintentar. Progreso "fragmento N de M" consultable. Bitácora en cada transición.

### Bloque 4 · Embeddings robustos
`EMBEDDINGS_TIMEOUT_S` (por defecto 300) en lugar de 30.0 fijo; lotes con `input` lista en `/api/embed` (`EMBEDDINGS_LOTE`, por defecto 16); 3 reintentos con espera; `keep_alive` para bge-m3. `uso_llm` registra por lote. Aplicar el mismo timeout configurable a la búsqueda del chat.

### Bloque 5 · Infraestructura
Versionar Garage: servicio `garage` en `compose.stage.yml` (`dxflrs/garage:v1.0.1`, binds `/srv/agente/garage/{meta,data}` y `garage.toml` de solo lectura, `red_interna`, sin puertos), plantilla `infra/garage/garage.toml.example` (`rpc_secret` generado, nunca en Git) y script idempotente `infra/scripts/inicializar-garage.sh` (layout, llave, buckets `conocimiento` y `documentos`). Quitar localstack de stage (se conserva en local). `.env.stage.example`: `MINIO_ENDPOINT=garage:3900`. Agregar `alembic==1.14.0` a `src/api/requirements.txt`. Revisar límites de memoria en `compose.stage.yml` (servicio con memory 64G y cpus 0.50; ollama 64G en VM de 60 GB → proponer 40–48G).

### Bloque 6 · Pruebas
PDF de 300 páginas: indexa en el worker sin "input too large", sin truncado y sin bloquear la API. Simular ReadTimeout y objeto ausente: la UI recibe mensaje y la fuente queda en `error_indexacion` con Reintentar. Reindexar CONT-006 y CONT-007. Regresión CU-01/CU-05/chat_kb. Resultados en `docs/04-pruebas/resultados/stage-P15.md`.

## 5. Reglas

TDD. Un commit por bloque (Conventional Commits) y push. Sin secretos ni `rpc_secret` en el repositorio. No mostrar archivos completos en el chat. Salida en chat por bloque: tabla ruta · cambio · prueba (ok/falla) · "¿Continúo con <siguiente>?".

Prioridad: los bloques 1, 2 y 4 desbloquean la aprobación en stage. Si en el bloque 3 hay riesgo para CU-01/CU-05 o para el chat de P-14, avisar antes de implementarlo.
