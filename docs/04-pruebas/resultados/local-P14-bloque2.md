# Resultados — P-14 (Chat de la Base de Conocimiento), Bloque 2 (API del chat)

**Versión:** 0.1.0
**Fecha:** 2026-10-13
**Relacionado con:** docs/05-prompts/P-14-chat-base-conocimiento.md, docs/04-pruebas/resultados/local-P14-bloque1.md, RF-23, RF-24, CU-12

## Alcance

4 endpoints (`POST /chat/conversaciones`, `GET /chat/conversaciones`, `GET /chat/conversaciones/{id}`, `POST /chat/conversaciones/{id}/mensajes`) que arman el prompt (pregunta + historial + fragmentos recuperados + texto de un adjunto opcional), generan la respuesta y la guardan -- reutilizando al máximo lo que ya existía (`rag.busqueda`, el motor de OCR de CU-06, los parsers de Word/PDF/Excel, `comun.uso_llm`).

## Cambios

| Archivo | Cambio |
| --- | --- |
| `src/comun/chat.py` (nuevo) | Lógica pura: `extraer_texto_adjunto` (dispatch por extensión -- imagen vía OCR, docx/xlsx vía sus parsers, pdf con texto nativo primero y OCR como respaldo si no tiene capa de texto), `fuentes_citadas` (estructura `fuente_id/versión/sección/página` por cada fragmento, `None` si no hubo ninguno -- nunca lista vacía), `construir_mensajes` (arma la lista de mensajes para el LLM: system + historial recortado a los últimos 10 + pregunta con los fragmentos y el texto del adjunto). El texto de un adjunto nunca se indexa en Qdrant ni se guarda como `FuenteConocimiento` (RF-24, R-18). |
| `src/comun/uso_llm.py` | `generar_respuesta_chat_con_registro`: como `envolver_generar_texto`, pero para una llamada única (no un `Callable` reutilizable) -- registra el uso del chat con `caso_uso="chat_kb"`. |
| `src/rag/cliente_llm.py` | `generar_respuesta_chat` ahora acepta `pensamiento`/`num_ctx`/`num_predict` (ver "Hallazgo" abajo). |
| `src/api/esquemas.py` | `ConversacionEsquema`, `FuenteCitadaEsquema`, `MensajeEsquema`, `RespuestaConversacionDetalle`. |
| `src/api/main.py` | Los 4 endpoints bajo `Depends(usuario_actual)` (sin permiso dedicado -- accesible a cualquier sesión, igual que Historial); `_conversacion_propia` devuelve 404 (no 403) si la conversación es de otro usuario o no existe, para no revelar su existencia (RNF-19). |
| `src/api/Dockerfile` | **Corrección real** (ver abajo): agrega Tesseract + `ocr/requirements.txt` -- la API ahora sí necesita el motor de OCR completo. |
| `tests/unit/test_chat.py` (nuevo, 13 pruebas) | `extraer_texto_adjunto` por cada extensión (incluyendo el respaldo a OCR en un PDF escaneado), `fuentes_citadas`, `construir_mensajes` (historial, recorte a 10 mensajes, marcador explícito de "sin fragmentos"). |
| `tests/unit/test_chat_endpoints.py` (nuevo, 10 pruebas) | Los 4 endpoints con un Qdrant real en memoria (`QdrantClient(":memory:")`) y embeddings falsos: cita la fuente cuando hay fragmento relevante, no inventa cuando no hay ninguno, aísla conversaciones entre usuarios (404), el adjunto nunca llega a `FuenteConocimiento` ni a Qdrant, y el uso se registra en `uso_llm`. |
| `tests/unit/test_cliente_llm.py`, `test_uso_llm.py` | +5 pruebas (historial completo, métricas, sin `format`/`think` de más, y el passthrough de `pensamiento`/`num_ctx`/`num_predict`). |

## Hallazgos reales durante la validación en vivo (no cosméticos)

1. **La imagen `api` no tenía `cv2`/Tesseract instalados.** `src/api/Dockerfile` excluía deliberadamente el motor de OCR completo (comentario propio: *"la API NO necesita el resto de `ocr` -- OpenCV/Tesseract viven solo en el worker"*), una decisión correcta hasta este bloque -- RF-24 ahora exige que la API procese un adjunto de imagen de forma síncrona. Corregido agregando el mismo bloque de instalación de Tesseract 5 + `tessdata_best` spa/eng que ya usa `orquestador/Dockerfile` (ADR-007), y `ocr/requirements.txt` al `pip install`.
2. **Un prompt de chat sin acotar superó el timeout de 300 s** contra `gpt-oss:20b` real (CPU, sin GPU) -- `generar_respuesta_chat` no aceptaba `pensamiento`/`num_ctx`/`num_predict` (se excluyeron por error junto con `formato`, que sí es irrelevante para el chat). Corregido: se agregaron esos tres parámetros (mismo mecanismo que ya usa CU-02) y el endpoint los usa (`pensamiento="low"`, `num_ctx=4096`, `num_predict=800`). Medido de nuevo en vivo: **2 min 44 s**, dentro del timeout.

## Resultados de pruebas (reales, no estimados)

- `ruff check` / `mypy` sobre `src` completo: sin hallazgos.
- `pytest tests/unit/test_chat.py tests/unit/test_chat_endpoints.py tests/unit/test_cliente_llm.py tests/unit/test_uso_llm.py`: **52 passed**.
- `pytest tests/unit` (suite completa, incluyendo la prueba del passthrough de `pensamiento`/`num_ctx`/`num_predict`): **704 passed** (678 del cierre de P-14 Bloque 1 + 26 de este bloque), cobertura 94 %, sin regresiones.

## Validación en vivo (Docker real)

- Reconstruida la imagen `api` (dos veces: una con el Dockerfile corregido, otra con el ajuste de latencia) y redesplegada.
- Flujo real completo como `analista@local`: crear conversación → enviar pregunta real ("¿Cuál es la política de cierre contable?") → respuesta real de `gpt-oss:20b` citando 2 fuentes reales de la Base de Conocimiento (`E2E-...`, `FUE-003`) en 2 min 44 s.
- `GET /admin/dashboard/consumo?caso_uso=chat_kb` (P-13) confirma la integración end-to-end: 2 llamadas registradas (1 `bge-m3` de la búsqueda, 1 `gpt-oss:20b` de la respuesta), ambas bajo `caso_uso="chat_kb"`.
- Datos de prueba (conversaciones, mensajes y filas de `uso_llm` de esta validación) borrados de la base real al terminar.

## Pendiente (explícitamente de otros bloques de P-14)

- Bloque 3 (Pantalla): chat en "/", "Nuevo análisis" se muda a su propia ruta.
- Bloque 4 (Pruebas y cierre): permisos (ya cubiertos aquí con el aislamiento 404 entre usuarios, falta la prueba formal de cierre), rendimiento del registro (RNF-15, igual criterio que P-13), documentación y guion de demo.
- No probado contra un adjunto de imagen real con Tesseract real (solo con OCR simulado en las pruebas unitarias/integración) -- validar en el Bloque 4 con una imagen real.

¿Continúo con el Bloque 3 (Pantalla: chat en "/", mover "Nuevo análisis")?
