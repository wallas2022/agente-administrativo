# Build context: src/ (no src/api/) para poder copiar el paquete compartido "comun".
# Ver infra/compose.yml (build.context: ../src, build.dockerfile: api/Dockerfile).
FROM python:3.12-slim

WORKDIR /app

COPY comun/requirements.txt ./comun/requirements.txt
COPY api/requirements.txt ./api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

COPY comun ./comun
COPY api ./api

EXPOSE 8000

# python -m (no el script "uvicorn" suelto) para que /app quede en sys.path
# y "import comun" / "import api" resuelvan como paquetes hermanos.
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
