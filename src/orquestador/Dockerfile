# Build context: src/ (no src/orquestador/) para poder copiar el paquete compartido
# "comun". Ver infra/compose.yml (build.context: ../src, dockerfile: orquestador/Dockerfile).
# Esta misma imagen se reutiliza para el servicio "worker" (celery) en infra/compose.yml.
FROM python:3.12-slim

WORKDIR /app

COPY comun/requirements.txt ./comun/requirements.txt
COPY orquestador/requirements.txt ./orquestador/requirements.txt
RUN pip install --no-cache-dir -r orquestador/requirements.txt

COPY comun ./comun
# El paquete real está anidado (src/orquestador/orquestador/) para que
# `python -m orquestador` funcione igual aquí que en un entorno local con
# "src/orquestador" en PYTHONPATH — ver pyproject.toml [tool.pytest.ini_options].
COPY orquestador/orquestador ./orquestador

CMD ["python", "-m", "orquestador"]
