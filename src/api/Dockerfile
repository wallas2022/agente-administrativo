# Build context: src/ (no src/api/) para poder copiar el paquete compartido "comun".
# Ver infra/compose.yml (build.context: ../src, build.dockerfile: api/Dockerfile).
FROM python:3.12-slim

WORKDIR /app

COPY comun/requirements.txt ./comun/requirements.txt
COPY api/requirements.txt ./api/requirements.txt
COPY parsers/requirements.txt ./parsers/requirements.txt
COPY ortografia/requirements.txt ./ortografia/requirements.txt
COPY rag/requirements.txt ./rag/requirements.txt
COPY curaduria/requirements.txt ./curaduria/requirements.txt
RUN pip install --no-cache-dir \
    -r api/requirements.txt \
    -r parsers/requirements.txt \
    -r ortografia/requirements.txt \
    -r rag/requirements.txt \
    -r curaduria/requirements.txt

COPY comun ./comun
COPY api ./api
# CU-05 (Bloque O4): POST /analisis/{id}/generar-corregido aplica las
# correcciones aceptadas de forma síncrona (sin LLM de por medio), así que
# la API necesita estos paquetes -- no solo el worker.
COPY parsers ./parsers
COPY ortografia ./ortografia
# Bloque K5 (CU-08): la pantalla del curador aprueba/indexa fuentes de
# forma síncrona (embeddings, no LLM generativo -- rápido, ver
# docs/04-pruebas/resultados/local-SKB.md), sin pasar por el worker.
COPY rag ./rag
COPY curaduria ./curaduria
# CU-02 (Bloque 1): la ruta SSE /analisis/{id}/mejorar-stream corre la fase
# 2 (LLM por párrafo + guardia de integridad) síncrona dentro de la propia
# conexión HTTP -- la API necesita estos validadores directamente, sin
# pasar por el paquete "orquestador" (ese registra tareas de Celery al
# importarse).
COPY validadores ./validadores
# Esa misma fase 2 reutiliza el glosario interno de CU-05 (comun.glosario,
# kb/glosario/glosario.csv) -- antes de este bloque la API no necesitaba
# kb/ en absoluto (solo orquestador/worker la tenían, ver su Dockerfile).
COPY --from=kb . ./kb
# CU-06 (Bloque 3): GET /documentos/{id}/ocr-docx genera el .docx resaltado
# de forma síncrona con `ocr.exportar_docx` (solo usa python-docx, ya
# instalado vía parsers/requirements.txt) -- la API NO necesita el resto de
# `ocr` (OpenCV/Tesseract viven solo en el worker, ver su Dockerfile).
COPY ocr ./ocr

EXPOSE 8000

# python -m (no el script "uvicorn" suelto) para que /app quede en sys.path
# y "import comun" / "import api" resuelvan como paquetes hermanos.
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
