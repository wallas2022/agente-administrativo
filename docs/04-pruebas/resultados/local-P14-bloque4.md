# Resultados — P-14 (Chat de la Base de Conocimiento), Bloque 4 (Pruebas y cierre)

**Versión:** 0.1.0
**Fecha:** 2026-10-13
**Relacionado con:** docs/05-prompts/P-14-chat-base-conocimiento.md, docs/04-pruebas/resultados/local-P14-bloque1.md..bloque3.md, HU-31..34, RF-23, RF-24, RNF-19

## Alcance

Cierre de P-14: permisos (cualquier rol autenticado, sin 403 propio), aislamiento de conversaciones entre usuarios, confirmación de que un adjunto nunca llega a la Base de Conocimiento, sobrecarga del registro de uso (mismo criterio que RNF-15/P-13) y validación en vivo de un adjunto de imagen real (pendiente desde el Bloque 2). Actualización de `plan-pruebas-prototipo.md`, `estado-proyecto.md`, `docs/06-operacion` y el guion de demo.

## Cambios

| Archivo | Cambio |
| --- | --- |
| `tests/unit/test_chat_endpoints.py` | +6 pruebas: los 5 roles (analista/revisor/curador/auditor/administrador) crean y listan conversaciones sin 403 (el chat no tiene permiso propio, a diferencia del Dashboard); con los 5 roles creando una conversación cada uno, cada quien ve exactamente la suya (RNF-19). |
| `docs/04-pruebas/plan-pruebas-prototipo.md` | PP-25 (acceso por cualquier rol), PP-26 (aislamiento entre usuarios), PP-27 (adjunto sin fuga a la Base de Conocimiento) -- con sus resultados reales. |
| `docs/04-pruebas/estado-proyecto.md` | CU-12 agregado a la tabla de casos de uso (P-14 completo); actualizado "Qué falta para escalar". |
| `docs/06-operacion/chat-base-conocimiento.md` (nuevo) | Por qué una pregunta puede tardar minutos (sin streaming, LLM en CPU) y qué revisar si tarda más de lo esperado; qué adjuntos acepta; por qué no hace falta una vista de monitoreo aparte (ya está en el Dashboard, `caso_uso=chat_kb`). |
| `docs/04-pruebas/guion-demo-sandbox.md` | Sección nueva "P-14 — Chat de la Base de Conocimiento", mismo formato que las secciones de P-12/P-13; tabla de usuarios actualizada (todos ven "Chat"). |

## Resultados de pruebas (reales, no estimados)

| Caso (plan de pruebas) | Prueba | Resultado | Cumple |
| --- | --- | --- | --- |
| PP-25 (acceso por cualquier rol) | 5 roles × `POST`/`GET /chat/conversaciones` | 0 rechazos (todos 200) | Sí |
| PP-26 (aislamiento entre usuarios) | 5 roles crean una conversación cada uno | Cada quien ve exactamente 1 (la suya), nunca las de otro -- más los 404 explícitos del Bloque 2 al pedir la de otro usuario por id | Sí |
| PP-27 (adjunto sin fuga a la Base de Conocimiento) | Adjunto de imagen real (Tesseract real) + adjunto de Word simulado (Bloque 2) | 0 filas nuevas en `fuente_conocimiento`, 0 puntos nuevos en Qdrant | Sí |
| RNF-15 (sobrecarga del registro, mismo criterio que P-13) | `registrar_uso_llm` no distingue por `caso_uso` -- ya medido en `local-P13-bloque5.md` (0.151 ms/llamada) | Sin sobrecarga adicional: el chat usa la misma función, el mismo código, sin rama especial | Sí (no vuelto a medir: sería remedir la misma función, no el chat en sí) |

- `ruff check` / `mypy` sobre `src`: sin hallazgos.
- `pytest tests/unit` (suite completa): **710 passed** (704 + 6 de este bloque), cobertura 94 %, sin regresiones.

## Validación en vivo (Docker real) -- adjunto de imagen real, pendiente desde el Bloque 2

Usando `tests/dataset/cu-06/legible_render_limpio.png` (imagen sintética de una factura, generada por `tests/dataset/generar_cu06.py`) como adjunto real de una pregunta ("¿Qué dice la imagen adjunta?"):
- El motor de OCR real (Tesseract, instalado en la API desde el Bloque 2) reconoció el texto de la imagen.
- El LLM respondió resumiendo correctamente el contenido real de la factura (número, proveedor, fecha, subtotal, IVA y total) -- confirma que el texto reconocido, no una alucinación, llegó al prompt.
- Tiempo real: **2 min 46 s** (consistente con la medición del Bloque 2, dentro del timeout de 300 s).
- Confirmado tras la prueba: 0 filas nuevas en `fuente_conocimiento` (las más recientes en la base real siguen siendo las de los specs E2E de curaduría, ninguna de esta prueba).
- Conversación, mensajes y filas de `uso_llm` de esta validación borrados de la base real al terminar.

## Definición de terminado (P-14, contra la sección 9 del prompt)

- Cualquier usuario autenticado puede preguntar en lenguaje natural sobre la Base de Conocimiento vigente y recibe una respuesta citada, o un "no tengo información" explícito -- Bloques 2-3, confirmado en vivo.
- Puede adjuntar una imagen o un documento a su pregunta, sin que ese archivo quede en la Base de Conocimiento permanente -- confirmado en vivo en este bloque (imagen real) y en el Bloque 2 (documento simulado).
- El chat sostiene una conversación con memoria y guarda el historial por usuario, sin exponer el de otros -- Bloques 1-2-4.
- El chat es la pantalla de inicio para todos los roles; "Nuevo análisis" sigue disponible en su propia ruta -- Bloque 3.
- No se origina ninguna llamada externa ni a internet -- por diseño (Ollama/Qdrant locales, mismo criterio que el resto del sistema, RNF-01); no se agregó una prueba de red dedicada en este bloque, igual que el resto de funcionalidades del proyecto que comparten esa misma garantía arquitectónica.

P-14 queda cerrado en ambiente local.
