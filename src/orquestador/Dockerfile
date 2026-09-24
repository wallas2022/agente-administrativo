# Dockerfile mínimo — sin lógica de negocio. Ver README.md de este módulo.
# Esta misma imagen se reutiliza para el servicio "worker" (celery) en infra/docker-compose.yml.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "orquestador"]
