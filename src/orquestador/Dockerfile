# Build context: src/ (no src/orquestador/) para poder copiar el paquete compartido
# "comun". Ver infra/compose.yml (build.context: ../src, dockerfile: orquestador/Dockerfile).
# Esta misma imagen se reutiliza para el servicio "worker" (celery) en infra/compose.yml.
# Contexto adicional "kb" (ver build.additional_contexts en infra/compose.yml): kb/ vive
# en la raíz del repo, fuera de src/, y el pipeline CU-01 la necesita en tiempo de
# ejecución (catálogo de cuentas, fuentes de la política de cierre).
FROM python:3.12-slim

WORKDIR /app

COPY comun/requirements.txt ./comun/requirements.txt
COPY orquestador/requirements.txt ./orquestador/requirements.txt
COPY parsers/requirements.txt ./parsers/requirements.txt
COPY rag/requirements.txt ./rag/requirements.txt
RUN pip install --no-cache-dir \
    -r orquestador/requirements.txt \
    -r parsers/requirements.txt \
    -r rag/requirements.txt

COPY comun ./comun
# Paquetes del pipeline CU-01 (Sprint 1) que orquestador.pipeline_contable importa
# en tiempo de ejecución del worker (parser → reglas → RAG → explicación → salida).
COPY parsers ./parsers
COPY rag ./rag
COPY validadores ./validadores
COPY --from=kb . ./kb
# El paquete real está anidado (src/orquestador/orquestador/) para que
# `python -m orquestador` funcione igual aquí que en un entorno local con
# "src/orquestador" en PYTHONPATH — ver pyproject.toml [tool.pytest.ini_options].
COPY orquestador/orquestador ./orquestador

CMD ["python", "-m", "orquestador"]
