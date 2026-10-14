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


class RespuestaMe(BaseModel):
    """P-12 (Bloque 1, HU-20): lo que la UI necesita para construir el menú
    y las rutas -- nunca la contraseña ni su hash."""

    id: str
    nombre: str
    email: str
    rol: str
    area: str
    permisos: list[str]  # "recurso:accion", ver docs/03-diseno/seguridad/roles-permisos.md v0.3
    debe_cambiar_password: bool


class SolicitudCambiarPassword(BaseModel):
    password_actual: str
    password_nueva: str


class RespuestaCambiarPassword(BaseModel):
    cambiada: bool


class UsuarioAdminEsquema(BaseModel):
    """P-12 (Bloque 4, HU-22): fila de Configuración → Usuarios -- nunca
    incluye password_hash ni la contraseña."""

    id: str
    nombre: str
    email: str
    rol: str
    area_id: str
    area: str
    activo: bool
    debe_cambiar_password: bool
    ultimo_acceso: datetime | None = None
    bloqueado_hasta: datetime | None = None


class SolicitudCrearUsuario(BaseModel):
    nombre: str
    email: str
    area_id: str
    rol: str


class RespuestaCrearUsuario(BaseModel):
    usuario: UsuarioAdminEsquema
    # Mostrada una sola vez en esta respuesta (HU-22); nunca se vuelve a
    # poder consultar -- solo "Restablecer contraseña" genera una nueva.
    password_temporal: str


class SolicitudEditarUsuario(BaseModel):
    nombre: str | None = None
    area_id: str | None = None
    rol: str | None = None
    activo: bool | None = None


class RespuestaPasswordTemporal(BaseModel):
    password_temporal: str


class PermisoMatrizEsquema(BaseModel):
    """Una celda de la matriz de Configuración → Roles y permisos (HU-23)."""

    rol: str
    recurso: str
    accion: str
    otorgado: bool
    protegido: bool


class SolicitudActualizarPermiso(BaseModel):
    rol: str
    recurso: str
    accion: str
    otorgado: bool


class AreaEsquema(BaseModel):
    id: str
    nombre: str


class SolicitudArea(BaseModel):
    nombre: str


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
    # Solo aplica a tipo_revision=="redaccion" (CU-02): tipo de documento
    # (Correo|Memo|Procedimiento|Informe -- solo "Procedimiento" activa RD-01,
    # ver validadores.redaccion.reglas) y acción (Corregir|Aclarar|Formalizar,
    # ver validadores.redaccion.mejora.ACCIONES_VALIDAS).
    tipo_documento: str | None = None
    accion: str | None = None


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


class HistorialItemEsquema(BaseModel):
    """P-12 (Bloque 3, HU-21): una fila de GET /historial -- a diferencia de
    RespuestaAnalisis (pantalla de un análisis puntual), trae quién lo
    corrió, su área, la duración ya calculada y el número de hallazgos."""

    id: str
    nombre_documento: str | None = None
    tipo_revision: str
    estado: str
    fecha_inicio: datetime
    fecha_fin: datetime | None = None
    duracion_segundos: float | None = None
    usuario_nombre: str
    usuario_email: str
    area_nombre: str
    numero_hallazgos: int


class RespuestaHistorial(BaseModel):
    total: int
    pagina: int
    tamano_pagina: int
    resultados: list[HistorialItemEsquema]


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


class SolicitudEditarTextoOcr(BaseModel):
    """CU-06 (Bloque 3): edición manual del texto reconocido por OCR."""

    texto: str


class RespuestaEditarTextoOcr(BaseModel):
    guardado: bool


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


class BitacoraGlobalEsquema(BaseModel):
    """P-12 (Bloque 2, HU-20): auditoría global para Administrador/Auditor
    (`bitacora:ver`) -- distinta de BitacoraEsquema, que es el detalle de
    pasos de UN análisis puntual (ver roles-permisos.md v0.3)."""

    id: str
    fecha_hora: datetime
    usuario_email: str
    usuario_nombre: str
    rol: str | None = None
    accion: str
    entidad_tipo: str
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
    fragmentos_total: int | None = None
    fragmentos_procesados: int | None = None
    motivo_error: str | None = None


class RespuestaAprobarFuente(BaseModel):
    fuente_id: str
    version: str
    estado: str


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


# --- Dashboard del Administrador (P-13, Bloque 3) ---------------------------


class TarjetasConsumoEsquema(BaseModel):
    tokens_entrada: int
    tokens_salida: int
    tokens_totales: int
    llamadas: int
    tokens_por_segundo_promedio: float | None = None
    pct_timeouts: float


class PuntoSerieDiariaEsquema(BaseModel):
    fecha: str
    tokens_entrada: int
    tokens_salida: int
    llamadas: int


class ItemRankingConsumoEsquema(BaseModel):
    """Una fila del ranking por caso de uso o por modelo (HU-28) -- solo
    uno de `caso_uso`/`modelo` viene lleno según cuál ranking es."""

    caso_uso: str | None = None
    modelo: str | None = None
    tokens_totales: int
    duracion_llm_total_ms: int
    llamadas: int
    duracion_media_analisis_ms: float | None = None


class RespuestaConsumo(BaseModel):
    tarjetas: TarjetasConsumoEsquema
    serie_diaria: list[PuntoSerieDiariaEsquema]
    ranking_caso_uso: list[ItemRankingConsumoEsquema]
    ranking_modelo: list[ItemRankingConsumoEsquema]


class FilaConsumoUsuarioEsquema(BaseModel):
    usuario_id: str
    usuario_nombre: str
    usuario_email: str
    area_nombre: str
    numero_analisis: int
    tokens_entrada: int
    tokens_salida: int
    duracion_llm_total_ms: int
    timeouts: int


class RecursosHostEsquema(BaseModel):
    cpu_ocupado_pct: float | None = None
    vcpus: int | None = None
    memoria_usada_bytes: int
    memoria_total_bytes: int
    disco_usado_bytes: int | None = None
    disco_total_bytes: int | None = None
    carga_1m: float | None = None


class RecursosContenedorEsquema(BaseModel):
    nombre: str
    cpu_pct: float
    memoria_usada_bytes: int | None = None
    memoria_limite_bytes: int | None = None
    memoria_pct_del_limite: float | None = None


class RecursosOllamaEsquema(BaseModel):
    # Se pasa tal cual lo que devuelve Ollama (/api/ps, /api/tags) -- forma
    # variable entre versiones, no se modela campo por campo.
    modelos_en_memoria: list[dict]
    modelos_instalados: list[dict]


class AlertaDashboardEsquema(BaseModel):
    tipo: str
    mensaje: str


class RespuestaRecursos(BaseModel):
    # False cuando Prometheus no está disponible (apagado por defecto en
    # local, perfil "observabilidad" -- ver ADR-009) -- la pantalla debe
    # mostrar un mensaje claro, no un error.
    prometheus_disponible: bool
    host: RecursosHostEsquema | None = None
    contenedores: list[RecursosContenedorEsquema] | None = None
    ollama: RecursosOllamaEsquema | None = None
    alertas: list[AlertaDashboardEsquema]


class RespuestaConfiguracion(BaseModel):
    variables: dict[str, str]
    app_version: str
    git_commit: str


# --- Chat de la Base de Conocimiento (P-14, Bloque 2, CU-12) ----------------


class ConversacionEsquema(BaseModel):
    id: str
    titulo: str | None = None
    fecha_creacion: datetime


class FuenteCitadaEsquema(BaseModel):
    fuente_id: str
    version: str
    seccion: str | None = None
    pagina: int | None = None


class MensajeEsquema(BaseModel):
    id: str
    rol: str
    contenido: str
    fecha_hora: datetime
    fuentes_citadas: list[FuenteCitadaEsquema] | None = None


class RespuestaConversacionDetalle(BaseModel):
    id: str
    titulo: str | None = None
    fecha_creacion: datetime
    mensajes: list[MensajeEsquema]
