# Build context: src/ (no src/api/) para poder copiar el paquete compartido "comun".
# Ver infra/compose.yml (build.context: ../src, build.dockerfile: api/Dockerfile).
FROM python:3.12-slim

WORKDIR /app

COPY comun/requirements.txt ./comun/requirements.txt
COPY api/requirements.txt ./api/requirements.txt
COPY parsers/requirements.txt ./parsers/requirements.txt
COPY ortografia/requirements.txt ./ortografia/requirements.txt
RUN pip install --no-cache-dir \
    -r api/requirements.txt \
    -r parsers/requirements.txt \
    -r ortografia/requirements.txt

COPY comun ./comun
COPY api ./api
# CU-05 (Bloque O4): POST /analisis/{id}/generar-corregido aplica las
# correcciones aceptadas de forma síncrona (sin LLM de por medio), así que
# la API necesita estos paquetes -- no solo el worker.
COPY parsers ./parsers
COPY ortografia ./ortografia

EXPOSE 8000

# python -m (no el script "uvicorn" suelto) para que /app quede en sys.path
# y "import comun" / "import api" resuelvan como paquetes hermanos.
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
