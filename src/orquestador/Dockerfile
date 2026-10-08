# Build context: src/ (no src/orquestador/) para poder copiar el paquete compartido
# "comun". Ver infra/compose.yml (build.context: ../src, dockerfile: orquestador/Dockerfile).
# Esta misma imagen se reutiliza para el servicio "worker" (celery) en infra/compose.yml.
# Contexto adicional "kb" (ver build.additional_contexts en infra/compose.yml): kb/ vive
# en la raíz del repo, fuera de src/, y el pipeline CU-01 la necesita en tiempo de
# ejecución (catálogo de cuentas, fuentes de la política de cierre).
FROM python:3.12-slim

WORKDIR /app

# Tesseract 5 + tessdata_best spa/eng (RF-11, CU-06, ADR-007). La imagen base
# ya trae osd.traineddata (detección de orientación) y un eng.traineddata
# rápido; tessdata_best da mejor exactitud, así que se reemplaza eng y se
# agrega spa -- ambos se descargan UNA sola vez, aquí, en el build (en local
# SÍ hay internet, ver infra/compose.local.yml; en CI/stage esta capa ya
# queda cacheada en el registro de imágenes). En tiempo de ejecución no se
# descarga nada (RNF-01, stage sin red). Si el layout de tessdata de la
# imagen base cambia, este RUN falla con "No such file or directory" antes
# de llegar a copiar el código de la aplicación -- nunca en silencio.
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
COPY orquestador/requirements.txt ./orquestador/requirements.txt
COPY parsers/requirements.txt ./parsers/requirements.txt
COPY rag/requirements.txt ./rag/requirements.txt
COPY ortografia/requirements.txt ./ortografia/requirements.txt
COPY ocr/requirements.txt ./ocr/requirements.txt
RUN pip install --no-cache-dir \
    -r orquestador/requirements.txt \
    -r parsers/requirements.txt \
    -r rag/requirements.txt \
    -r ortografia/requirements.txt \
    -r ocr/requirements.txt

COPY comun ./comun
# Paquetes de los pipelines CU-01 (Sprint 1), CU-05 (Bloque O4) y CU-06
# (Bloque 1) que orquestador.pipeline_contable/pipeline_ortografia/
# pipeline_ocr importan en tiempo de ejecución del worker.
COPY parsers ./parsers
COPY rag ./rag
COPY validadores ./validadores
COPY ortografia ./ortografia
COPY ocr ./ocr
COPY --from=kb . ./kb
# El paquete real está anidado (src/orquestador/orquestador/) para que
# `python -m orquestador` funcione igual aquí que en un entorno local con
# "src/orquestador" en PYTHONPATH — ver pyproject.toml [tool.pytest.ini_options].
COPY orquestador/orquestador ./orquestador

CMD ["python", "-m", "orquestador"]
