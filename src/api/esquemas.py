"""Esquemas Pydantic de la API (request/response). Sin lógica de negocio."""

from datetime import date, datetime

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
    # "AAAA-MM": período contable que se está cerrando/revisando (RN-03), no la
    # fecha en que se ejecuta el análisis. Solo aplica a tipo_revision=="contable"
    # -- CU-05 (ortografía) no tiene período de cierre.
    periodo_cierre: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class RespuestaCompletarCarga(BaseModel):
    documento_id: str
    analisis_id: str
    estado: str


class RespuestaAnalisis(BaseModel):
    id: str
    documento_id: str
    nombre_documento: str | None = None
    tipo_revision: str
    estado: str
    fecha_inicio: datetime
    fecha_fin: datetime | None = None
    periodo_cierre: str | None = None
    total_debe: float | None = None
    total_haber: float | None = None
    moneda: str | None = None
    # Calculado en el servidor (rol + segregación de funciones configurable,
    # SRS v0.9: SEGREGACION_APROBACION) para que la UI no duplique esa
    # lógica de negocio — ver decidir_hallazgo en api/main.py.
    puede_decidir: bool = False
    tiene_version_corregida: bool = False


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
    fuente_citada: str | None = None
    referencia_citada: str | None = None


class SolicitudDecision(BaseModel):
    resultado: str  # "aceptado" | "rechazado" | "deshecho"
    comentario: str | None = None


class RespuestaDecision(BaseModel):
    id: str
    hallazgo_id: str
    resultado: str
    fecha: datetime


class RespuestaGenerarCorregido(BaseModel):
    # False cuando ningún hallazgo está "aceptado" todavía -- no hay nada
    # que aplicar (RF-14, CU-05).
    generado: bool


class BitacoraEsquema(BaseModel):
    id: str
    accion: str
    fecha_hora: datetime
    detalle: str | None = None


class AjusteAutoaprobadoEsquema(BaseModel):
    """SRS v0.9 (RG-06, PP-09): una fila del reporte "Ajustes autoaprobados"
    -- un hallazgo de CU-01 (contable) que el mismo usuario que cargó el
    documento decidió sobre sí mismo."""

    fecha_hora: datetime
    usuario_email: str
    usuario_nombre: str
    rol: str | None = None
    documento_id: str
    documento_nombre: str
    analisis_id: str
    hallazgo_id: str
    hallazgo_descripcion: str
    resultado: str
    comentario: str | None = None


class FuenteConocimientoEsquema(BaseModel):
    id: str
    fuente_id: str
    titulo: str
    tipo: str
    version: str
    vigente_desde: date


# --- Bloque K5 (RF-16, CU-08): pantalla del curador -------------------------


class FuenteCuraduriaEsquema(BaseModel):
    id: str
    fuente_id: str
    titulo: str
    tipo: str
    prioridad: int
    version: str
    vigente_desde: date
    estado: str
    area_id: str
    dueno: str
    archivo: str
    sha256: str | None = None
    cargado_por: str
    aprobado_por: str | None = None
    fecha_carga: datetime
    fecha_aprobacion: datetime | None = None


class RespuestaAprobarFuente(BaseModel):
    fuente_id: str
    version: str
    fragmentos_indexados: int
    duracion_segundos: float
    version_anterior_obsoleta: bool


class FragmentoVistaPreviaEsquema(BaseModel):
    contenido: str
    seccion: str | None = None
    pagina: int | None = None


class RespuestaVistaPrevia(BaseModel):
    fragmentos: list[FragmentoVistaPreviaEsquema]


class GlosarioEsquema(BaseModel):
    id: str
    termino: str
    definicion: str
    area_id: str
    fuente_id: str | None = None
    version: str | None = None
    vigente_desde: date | None = None


class SolicitudGlosario(BaseModel):
    termino: str = Field(min_length=1, max_length=200)
    definicion: str = Field(min_length=1)


class ErrorImportacionEsquema(BaseModel):
    hoja: str
    fila: int | None = None
    columna: str | None = None
    mensaje: str


class RespuestaValidarPlantilla(BaseModel):
    es_valido: bool
    errores: list[ErrorImportacionEsquema]
    resumen: dict[str, int]


class RespuestaImportarPlantilla(BaseModel):
    es_valido: bool
    errores: list[ErrorImportacionEsquema]
    cargado: dict[str, int] | None = None
