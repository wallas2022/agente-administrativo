"""Esquemas Pydantic de la API (request/response). Sin lógica de negocio."""

from datetime import datetime

from pydantic import BaseModel, Field


class SolicitudLogin(BaseModel):
    email: str
    password: str


class RespuestaToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rol: str


class SolicitudIniciarCarga(BaseModel):
    nombre_original: str
    tipo_archivo: str
    tamano_bytes: int = Field(gt=0)


class RespuestaIniciarCarga(BaseModel):
    documento_id: str
    upload_id: str
    llave_almacenamiento: str


class ParteSubidaEsquema(BaseModel):
    numero_parte: int
    etag: str


class SolicitudCompletarCarga(BaseModel):
    partes: list[ParteSubidaEsquema]
    tipo_revision: str


class RespuestaCompletarCarga(BaseModel):
    documento_id: str
    analisis_id: str
    estado: str


class RespuestaAnalisis(BaseModel):
    id: str
    documento_id: str
    tipo_revision: str
    estado: str
    fecha_inicio: datetime
    fecha_fin: datetime | None = None


class HallazgoEsquema(BaseModel):
    id: str
    regla_codigo: str | None = None
    severidad: str
    ubicacion: str
    descripcion: str
    correccion_sugerida: str | None = None
    monto: float | None = None
    moneda: str | None = None
    estado: str


class SolicitudDecision(BaseModel):
    resultado: str  # "aceptado" | "rechazado" | "deshecho"
    comentario: str | None = None


class RespuestaDecision(BaseModel):
    id: str
    hallazgo_id: str
    resultado: str
    fecha: datetime
