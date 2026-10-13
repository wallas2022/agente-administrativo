# Resultados — P-14 (Chat de la Base de Conocimiento), Bloque 1 (Modelo de datos y generación multi-turno)

**Versión:** 0.1.0
**Fecha:** 2026-10-13
**Relacionado con:** docs/05-prompts/P-14-chat-base-conocimiento.md, docs/02-analisis/07-analisis-chat-base-conocimiento.md, RF-23, CU-12

## Alcance

Base para el chat de la Base de Conocimiento: tablas `conversacion`/`mensaje` y una función nueva en `rag/cliente_llm.py` que acepta el historial completo de una conversación (multi-turno), sin tocar el contrato de las funciones ya existentes.

## Cambios

| Archivo | Cambio |
| --- | --- |
| `src/comun/modelos.py` | Modelos nuevos `Conversacion` (usuario_id, titulo, fecha_creacion) y `Mensaje` (conversacion_id, rol `user`/`assistant`, contenido, fecha_hora, `fuentes_citadas` JSON opcional), con sus índices por `usuario_id`/`conversacion_id`. |
| `src/api/migraciones/versions/7fcc343bac6f_conversacion_mensaje_p14_bloque1.py` (nueva) | Migración Alembic (down_revision `0806306a1cc8`, la de P-13 Bloque 1), autogenerada y aplicada contra el Postgres real local; verificada reversible (`downgrade -1` + `upgrade head`). |
| `src/rag/cliente_llm.py` | Extraído `_generar_con_mensajes()` (transporte HTTP + métricas) de `generar_texto_con_metricas`, que ahora es un wrapper delgado sobre esa función; agregada `generar_respuesta_chat(mensajes, ...)`, que acepta una lista de mensajes (`system`/`user`/`assistant`) en vez de un único prompt -- mismo transporte (`/api/chat`) y mismo registro de métricas (`MetricasOllama`) que el resto del proyecto. `generar_texto`/`generar_texto_con_metricas` no cambiaron de firma ni de comportamiento. |
| `tests/unit/test_cliente_llm.py` | 4 pruebas nuevas: el historial completo se manda tal cual a `/api/chat`, las métricas se exponen igual que con un prompt de una sola pasada, no se mandan `format`/`think` (el chat siempre responde texto libre), y se respeta `keep_alive`/`temperature`/`seed` igual que el resto de llamadas al LLM. |

## Resultados de pruebas (reales, no estimados)

- `ruff check` / `mypy` sobre `rag/cliente_llm.py` y `comun/modelos.py`: sin hallazgos.
- `pytest tests/unit/test_cliente_llm.py`: **19 passed** (15 previas + 4 nuevas).
- `pytest tests/unit` (suite completa): **678 passed** (674 del cierre de P-13 + 4 de este bloque), cobertura 94 %, sin regresiones.
- Migración verificada contra Postgres real: `alembic upgrade head` (aplica), `alembic downgrade -1` (revierte sin error), `alembic upgrade head` (vuelve a aplicar sin error).

## Pendiente (explícitamente de otros bloques de P-14)

- Bloque 2 (API del chat): endpoints `POST /chat/conversaciones`, `GET /chat/conversaciones`, `GET /chat/conversaciones/{id}`, `POST /chat/conversaciones/{id}/mensajes` -- con recuperación RAG, adjuntos (OCR/parsers) y registro en `uso_llm`.
- Bloque 3 (Pantalla): chat en "/", "Nuevo análisis" se muda a su propia ruta.
- Bloque 4 (Pruebas y cierre): permisos de aislamiento entre usuarios, rendimiento del registro, documentación.

¿Continúo con el Bloque 2 (API del chat)?
