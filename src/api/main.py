# Esqueleto de la API. Sin lógica de negocio: solo interfaz y healthcheck.
# Relacionado con: RF-01, RF-12, RF-13, RF-17, RF-18 (ver README.md de este módulo)
from fastapi import FastAPI

app = FastAPI(title="Agente Administrativo — API")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
