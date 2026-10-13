# Build context: src/ (no src/api/) para poder copiar el paquete compartido "comun".
# Ver infra/compose.yml (build.context: ../src, build.dockerfile: api/Dockerfile).
FROM python:3.12-slim

WORKDIR /app

# P-13 (Bloque 3, HU-30): versión/commit de la app para la pantalla de
# Configuración del Dashboard -- "build arg", no leído de un archivo en
# tiempo de ejecución (no hay git disponible dentro del contenedor). Sin
# pasar --build-arg, quedan en "sin-confirmar" (nunca inventados).
ARG APP_VERSION=sin-confirmar
ARG GIT_COMMIT=sin-confirmar
ENV APP_VERSION=${APP_VERSION}
ENV GIT_COMMIT=${GIT_COMMIT}

# P-14 (Bloque 2, RF-24): el chat de la Base de Conocimiento procesa un
# adjunto de imagen de forma síncrona (OCR, dentro de la misma llamada
# HTTP) -- antes de este bloque la API solo necesitaba `ocr.exportar_docx`
# (python-docx puro); ahora también necesita el motor real. Mismo bloque de
# instalación que orquestador/Dockerfile (Tesseract 5 + tessdata_best
# spa/eng, ADR-007) -- ver ese archivo para el detalle de cada paso.
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr curl \
    && test -f "$TESSDATA_PREFIX/osd.traineddata" \
    && curl -fsSL -o "$TESSDATA_PREFIX/spa.traineddata" \
        https://github.com/tesseract-ocr/tessdata_best/raw/main/spa.traineddata \
    && curl -fsSL -o "$TESSDATA_PREFIX/eng.traineddata" \
        https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata \
    && test -f "$TESSDATA_PREFIX/spa.traineddata" \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY comun/requirements.txt ./comun/requirements.txt
COPY api/requirements.txt ./api/requirements.txt
COPY parsers/requirements.txt ./parsers/requirements.txt
COPY ortografia/requirements.txt ./ortografia/requirements.txt
COPY rag/requirements.txt ./rag/requirements.txt
COPY curaduria/requirements.txt ./curaduria/requirements.txt
COPY ocr/requirements.txt ./ocr/requirements.txt
RUN pip install --no-cache-dir \
    -r api/requirements.txt \
    -r parsers/requirements.txt \
    -r ortografia/requirements.txt \
    -r rag/requirements.txt \
    -r curaduria/requirements.txt \
    -r ocr/requirements.txt

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
# de forma síncrona con `ocr.exportar_docx` (solo usa python-docx). P-14
# (Bloque 2, RF-24) agrega el motor completo (`ocr.motor`/`ocr.documentos`):
# ya no es cierto que "la API no necesita el resto de ocr" -- ver el bloque
# de instalación de Tesseract arriba.
COPY ocr ./ocr

EXPOSE 8000

# python -m (no el script "uvicorn" suelto) para que /app quede en sys.path
# y "import comun" / "import api" resuelvan como paquetes hermanos.
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
