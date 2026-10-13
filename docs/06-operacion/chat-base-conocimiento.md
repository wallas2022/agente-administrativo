# Chat de la Base de Conocimiento

**Versión:** 0.1.0
**Fecha:** 2026-10-13
**Relacionado con:** HU-31..34, RF-23, RF-24, docs/04-pruebas/resultados/local-P14-bloque2.md..bloque4.md

Notas operativas para quien administra el servicio -- no es un manual de usuario (la pantalla misma explica cómo usarla).

## Por qué una pregunta puede tardar minutos

El chat no usa streaming: la API espera a que el LLM termine de generar toda la respuesta antes de devolver algo al navegador. Contra `gpt-oss:20b` en hardware sin GPU, una pregunta real puede tardar entre varios segundos y un par de minutos (medido en vivo: 2 min 44 s en el caso más lento documentado, ver `local-P14-bloque2.md`). La pantalla muestra "El asistente está pensando…" mientras tanto -- no es que el servicio esté caído.

Si una pregunta tarda sistemáticamente mucho más que eso (varios minutos o más):
- Confirmar que Ollama tiene el modelo cargado (`OLLAMA_KEEP_ALIVE`, pestaña Configuración del Dashboard) -- si el modelo se descargó de memoria entre preguntas, la siguiente llamada paga el costo de cargarlo de nuevo.
- Revisar la pestaña Recursos del Dashboard (CPU/memoria del host y del contenedor de Ollama).
- El endpoint usa `pensamiento="low"` y limita el contexto/la salida (`num_ctx=4096`, `num_predict=800`) para acotar el tiempo -- no se puede bajar más sin perder calidad de respuesta; si hace falta ajustar estos valores, está en `api/main.py::enviar_mensaje_chat`.

## Qué adjuntos acepta

Imágenes (`png`, `jpg`, `jpeg`, `tiff`, `tif`, `bmp`, vía OCR -- mismo motor que CU-06) y documentos (`docx`, `xlsx`, `pdf` -- con el mismo respaldo a OCR que el resto del sistema si un PDF no tiene capa de texto). El texto extraído se usa solo para esa pregunta puntual: nunca se indexa en Qdrant ni se agrega a la Base de Conocimiento permanente (eso sigue siendo exclusivo de CU-08, con su flujo de curaduría y aprobación).

## Qué NO monitorear acá

El consumo de tokens, duración y timeouts del chat ya se ve en el Dashboard del Administrador (`GET /admin/dashboard/consumo?caso_uso=chat_kb`) -- no hace falta una vista aparte.
