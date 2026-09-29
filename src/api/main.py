"""API (FastAPI) — esqueleto funcional de L2.

Cubre: /health, autenticación con usuarios locales de prueba (RF-01), carga de
documentos por partes y reanudable a MinIO (RF-03, RN-09), creación de un
análisis en cola (RF-04) y consulta de su estado (RF-18). Sin validadores de
negocio todavía (Sprint 1). Relacionado con docs/03-diseno/c4/02-contenedores.md,
docs/03-diseno/secuencia/cu-01-excel-contable.md.
"""

import hashlib
import mimetypes
import os
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from qdrant_client import QdrantClient
from sqlalchemy.orm import Session

from api.esquemas import (
    BitacoraEsquema,
    ErrorImportacionEsquema,
    FragmentoVistaPreviaEsquema,
    FuenteConocimientoEsquema,
    FuenteCuraduriaEsquema,
    GlosarioEsquema,
    HallazgoEsquema,
    ParteSubidaEsquema,
    RespuestaAnalisis,
    RespuestaAprobarFuente,
    RespuestaCompletarCarga,
    RespuestaDecision,
    RespuestaGenerarCorregido,
    RespuestaImportarPlantilla,
    RespuestaIniciarCarga,
    RespuestaToken,
    RespuestaValidarPlantilla,
    RespuestaVistaPrevia,
    SolicitudCompletarCarga,
    SolicitudDecision,
    SolicitudGlosario,
    SolicitudIniciarCarga,
    SolicitudLogin,
)
from comun import almacenamiento
from comun.cola import encolar_analisis
from comun.db import obtener_fabrica_sesion, obtener_sesion
from comun.estados import EstadoAnalisis, EstadoDocumento, RolUsuario
from comun.modelos import (
    Analisis,
    Area,
    Bitacora,
    Decision,
    Documento,
    FuenteConocimiento,
    Glosario,
    Hallazgo,
    TipoRevision,
    Usuario,
    VersionDocumento,
)
from comun.seguridad import (
    UsuarioLocal,
    autenticar_usuario_local,
    crear_token_acceso,
    decodificar_token_acceso,
)
from comun.semillas import sembrar_datos_de_prueba
from curaduria.extraccion import PdfSinTextoError, extraer_fragmentos
from curaduria.fuentes import aprobar_fuente, clasificar_tipo_fuente, prioridad_de_tipo
from curaduria.indexacion import (
    COLECCION_KB,
    desactivar_fragmentos_de_fuente,
    indexar_fuente,
)
from curaduria.plantilla import ResultadoImportacion, cargar_plantilla, leer_plantilla
from ortografia.generar_corregido import generar_documento_corregido
from rag.cliente_embeddings import DIMENSION_BGE_M3, obtener_embedding


@asynccontextmanager
async def _ciclo_de_vida(_app: FastAPI) -> AsyncIterator[None]:
    # En local/desarrollo (APP_ENV=local en .env.local) este startup deja el ambiente
    # listo para usarse de inmediato — se omite en cualquier otro valor, incluido "sin
    # definir" (pruebas unitarias, que ya preparan su propia sesión/bucket mockeados):
    # - RF-01: siembra los usuarios locales de prueba (uno por rol) como fila real.
    # - RF-03: crea el bucket de documentos si todavía no existe (en stage, la
    #   creación del bucket es un paso de aprovisionamiento de infraestructura,
    #   no responsabilidad del código de la aplicación).
    if os.environ.get("APP_ENV") == "local":
        sesion = obtener_fabrica_sesion()()
        try:
            sembrar_datos_de_prueba(sesion)
        finally:
            sesion.close()
        almacenamiento.asegurar_bucket(almacenamiento.obtener_cliente_s3(), BUCKET_DOCUMENTOS)
        almacenamiento.asegurar_bucket(almacenamiento.obtener_cliente_s3(), BUCKET_CONOCIMIENTO)
    yield


app = FastAPI(title="Agente Administrativo — API", lifespan=_ciclo_de_vida)

# Orígenes de src/ui (`npm run dev` en 5173, o la app ya compilada) — la API y la
# UI no comparten origen (ni Traefik enruta ambas bajo el mismo host todavía),
# así que sin esto el navegador bloquea las llamadas por CORS.
_origenes_ui = os.environ.get(
    "UI_ORIGENES_PERMITIDOS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origenes_ui,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Sin esto, el navegador recibe el header pero no lo expone a JS (fetch
    # ve `null` en Content-Disposition) — se notó al descargar el Excel
    # corregido: el archivo llegaba bien, pero con un nombre genérico.
    expose_headers=["Content-Disposition"],
)

_esquema_bearer = HTTPBearer()

BUCKET_DOCUMENTOS = os.environ.get("MINIO_BUCKET_DOCUMENTOS", "documentos")
# Bloque K5: binarios de fuentes de la base de conocimiento -- bucket aparte
# porque, a diferencia de "documentos", no está sujeto a la retención de 90
# días (RN-08); una fuente vigente persiste indefinidamente.
BUCKET_CONOCIMIENTO = os.environ.get("MINIO_BUCKET_CONOCIMIENTO", "conocimiento")


# --- Dependencias (sobreescribibles en pruebas vía app.dependency_overrides) ---


def obtener_cliente_almacenamiento():  # pragma: no cover - override en pruebas
    return almacenamiento.obtener_cliente_s3()


def obtener_encolador() -> Callable[[str, str], str]:  # pragma: no cover - override en pruebas
    return encolar_analisis


def obtener_cliente_qdrant() -> QdrantClient:  # pragma: no cover - override en pruebas
    # Mismo patrón que orquestador.tareas.analizar_documento.
    host = os.environ.get("QDRANT_HOST", "qdrant")
    puerto = os.environ.get("QDRANT_PORT", "6333")
    return QdrantClient(url=f"http://{host}:{puerto}")


def obtener_funcion_embedding() -> Callable[[str], list[float]]:  # pragma: no cover
    return obtener_embedding


def obtener_coleccion_kb() -> str:
    return os.environ.get("QDRANT_COLECCION", COLECCION_KB)


def usuario_actual(
    credenciales: Annotated[HTTPAuthorizationCredentials, Depends(_esquema_bearer)],
    sesion: Annotated[Session, Depends(obtener_sesion)],
) -> Usuario:
    try:
        datos = decodificar_token_acceso(credenciales.credentials)
    except PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido o expirado"
        ) from exc

    usuario = sesion.query(Usuario).filter_by(email=datos["email"]).one_or_none()
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado"
        )
    return usuario


def requiere_rol(*roles: RolUsuario) -> Callable[..., Usuario]:
    def dependencia(usuario: Annotated[Usuario, Depends(usuario_actual)]) -> Usuario:
        if usuario.rol_id is None or RolUsuario(_nombre_rol(usuario)) not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El rol del usuario no tiene permiso para esta acción",
            )
        return usuario

    return dependencia


def _nombre_rol(usuario: Usuario) -> str:
    # `Usuario.rol` no se carga automáticamente (sin relationship, ver modelos.py);
    # se resuelve por email como fixture de prueba (RF-01: usuarios locales).
    usuario_local: UsuarioLocal | None = None
    from comun.seguridad import obtener_usuario_de_prueba

    usuario_local = obtener_usuario_de_prueba(usuario.email)
    if usuario_local is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rol desconocido")
    return usuario_local.rol.value


# --- Endpoints ---


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/auth/login", response_model=RespuestaToken)
def login(datos: SolicitudLogin) -> RespuestaToken:
    usuario = autenticar_usuario_local(datos.email, datos.password)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas"
        )
    token = crear_token_acceso(email=usuario.email, rol=usuario.rol)
    return RespuestaToken(access_token=token, rol=usuario.rol.value)


@app.post("/documentos/iniciar", response_model=RespuestaIniciarCarga)
def iniciar_carga(
    datos: SolicitudIniciarCarga,
    usuario: Annotated[
        Usuario, Depends(requiere_rol(RolUsuario.ANALISTA, RolUsuario.ADMINISTRADOR))
    ],
    sesion: Annotated[Session, Depends(obtener_sesion)],
    cliente_s3: Annotated[object, Depends(obtener_cliente_almacenamiento)],
) -> RespuestaIniciarCarga:
    try:
        almacenamiento.validar_tamano(datos.tamano_bytes)
    except almacenamiento.ArchivoDemasiadoGrandeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        ) from exc

    documento = Documento(
        nombre_original=datos.nombre_original,
        tipo_archivo=datos.tipo_archivo,
        tamano_bytes=datos.tamano_bytes,
        area_id=usuario.area_id,
        usuario_carga_id=usuario.id,
        fecha_carga=datetime.now(UTC),
        fecha_expiracion=date.today() + timedelta(days=90),  # RN-08
        estado=EstadoDocumento.CARGADO.value,
    )
    sesion.add(documento)
    sesion.commit()

    llave = f"{usuario.area_id}/{documento.id}/{datos.nombre_original}"
    upload_id = almacenamiento.iniciar_carga_multiparte(cliente_s3, BUCKET_DOCUMENTOS, llave)

    return RespuestaIniciarCarga(
        documento_id=str(documento.id), upload_id=upload_id, llave_almacenamiento=llave
    )


@app.put("/documentos/{documento_id}/partes/{numero_parte}")
async def subir_parte_documento(
    documento_id: str,
    numero_parte: int,
    upload_id: str,
    llave_almacenamiento: str,
    request: Request,
    usuario: Annotated[
        Usuario, Depends(requiere_rol(RolUsuario.ANALISTA, RolUsuario.ADMINISTRADOR))
    ],
    cliente_s3: Annotated[object, Depends(obtener_cliente_almacenamiento)],
) -> dict:
    datos = await request.body()
    parte = almacenamiento.subir_parte(
        cliente_s3, BUCKET_DOCUMENTOS, llave_almacenamiento, upload_id, numero_parte, datos
    )
    return {"numero_parte": parte["PartNumber"], "etag": parte["ETag"]}


@app.get("/documentos/{documento_id}/partes", response_model=list[ParteSubidaEsquema])
def listar_partes_subidas_documento(
    documento_id: str,
    upload_id: str,
    llave_almacenamiento: str,
    usuario: Annotated[
        Usuario, Depends(requiere_rol(RolUsuario.ANALISTA, RolUsuario.ADMINISTRADOR))
    ],
    cliente_s3: Annotated[object, Depends(obtener_cliente_almacenamiento)],
) -> list[ParteSubidaEsquema]:
    """RN-09: permite reanudar una carga interrumpida preguntando qué partes
    ya llegaron a S3, en vez de volver a subir el archivo completo."""
    partes = almacenamiento.listar_partes_subidas(
        cliente_s3, BUCKET_DOCUMENTOS, llave_almacenamiento, upload_id
    )
    return [
        ParteSubidaEsquema(numero_parte=p["PartNumber"], etag=p["ETag"]) for p in partes
    ]


@app.post("/documentos/{documento_id}/completar", response_model=RespuestaCompletarCarga)
def completar_carga(
    documento_id: str,
    upload_id: str,
    llave_almacenamiento: str,
    datos: SolicitudCompletarCarga,
    usuario: Annotated[
        Usuario, Depends(requiere_rol(RolUsuario.ANALISTA, RolUsuario.ADMINISTRADOR))
    ],
    sesion: Annotated[Session, Depends(obtener_sesion)],
    cliente_s3: Annotated[object, Depends(obtener_cliente_almacenamiento)],
    encolar: Annotated[Callable[[str, str], str], Depends(obtener_encolador)],
) -> RespuestaCompletarCarga:
    documento = sesion.get(Documento, uuid.UUID(documento_id))
    if documento is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento no encontrado")

    # RN-03 necesita periodo_cierre para comparar la fecha de cada partida --
    # sin este chequeo, la falta del campo solo se descubriría más tarde,
    # como una excepción dentro del worker (ver pipeline_contable.py).
    if datos.tipo_revision == "contable" and not datos.periodo_cierre:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="periodo_cierre es obligatorio para tipo_revision='contable'",
        )

    partes: list[almacenamiento.ParteSubida] = [
        {"PartNumber": p.numero_parte, "ETag": p.etag} for p in datos.partes
    ]
    almacenamiento.completar_carga_multiparte(
        cliente_s3, BUCKET_DOCUMENTOS, llave_almacenamiento, upload_id, partes
    )

    sesion.add(
        VersionDocumento(
            documento_id=documento.id,
            numero_version=1,
            ruta_almacenamiento=llave_almacenamiento,
            es_corregida=False,
            fecha_creacion=datetime.now(UTC),
        )
    )

    tipo_revision = sesion.query(TipoRevision).filter_by(nombre=datos.tipo_revision).one_or_none()
    if tipo_revision is None:
        tipo_revision = TipoRevision(nombre=datos.tipo_revision)
        sesion.add(tipo_revision)
        sesion.flush()

    analisis = Analisis(
        documento_id=documento.id,
        tipo_revision_id=tipo_revision.id,
        usuario_id=usuario.id,
        fecha_inicio=datetime.now(UTC),
        estado=EstadoAnalisis.PROCESANDO.value,
        periodo_cierre=datos.periodo_cierre,
    )
    sesion.add(analisis)
    sesion.commit()

    encolar(str(documento.id), str(analisis.id))

    return RespuestaCompletarCarga(
        documento_id=str(documento.id), analisis_id=str(analisis.id), estado=documento.estado
    )


def _analisis_y_documento_accesibles(
    sesion: Session, usuario: Usuario, analisis_id: str, *, mensaje_403: str
) -> tuple[Analisis, Documento | None]:
    analisis = sesion.get(Analisis, uuid.UUID(analisis_id))
    if analisis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Análisis no encontrado")

    documento = sesion.get(Documento, analisis.documento_id)
    if _nombre_rol(usuario) not in (RolUsuario.ADMINISTRADOR.value, RolUsuario.AUDITOR.value):
        if documento is None or documento.area_id != usuario.area_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=mensaje_403)
    return analisis, documento


def _puede_decidir(usuario: Usuario, documento: Documento | None) -> bool:
    """Mismo criterio que decidir_hallazgo: rol Revisor/Administrador y no
    ser quien cargó el documento (RN-07, PP-09)."""
    if _nombre_rol(usuario) not in (RolUsuario.REVISOR.value, RolUsuario.ADMINISTRADOR.value):
        return False
    if documento is not None and documento.usuario_carga_id == usuario.id:
        return False
    return True


def _a_respuesta_analisis(
    sesion: Session, analisis: Analisis, documento: Documento | None, usuario: Usuario
) -> RespuestaAnalisis:
    tipo_revision = sesion.get(TipoRevision, analisis.tipo_revision_id)
    tiene_version_corregida = (
        sesion.query(VersionDocumento)
        .filter_by(documento_id=analisis.documento_id, es_corregida=True)
        .first()
        is not None
    )
    return RespuestaAnalisis(
        id=str(analisis.id),
        documento_id=str(analisis.documento_id),
        nombre_documento=documento.nombre_original if documento else None,
        tipo_revision=tipo_revision.nombre if tipo_revision else "",
        estado=documento.estado if documento else analisis.estado,
        fecha_inicio=analisis.fecha_inicio,
        fecha_fin=analisis.fecha_fin,
        periodo_cierre=analisis.periodo_cierre,
        total_debe=float(analisis.total_debe) if analisis.total_debe is not None else None,
        total_haber=float(analisis.total_haber) if analisis.total_haber is not None else None,
        moneda=analisis.moneda,
        puede_decidir=_puede_decidir(usuario, documento),
        tiene_version_corregida=tiene_version_corregida,
    )


@app.get("/analisis", response_model=list[RespuestaAnalisis])
def listar_analisis(
    usuario: Annotated[Usuario, Depends(usuario_actual)],
    sesion: Annotated[Session, Depends(obtener_sesion)],
    limite: int = 20,
) -> list[RespuestaAnalisis]:
    """Panel de "análisis recientes": del área del usuario, o de todas para
    Administrador/Auditor (mismo criterio que consultar_analisis)."""
    consulta = sesion.query(Analisis).join(Documento, Analisis.documento_id == Documento.id)
    if _nombre_rol(usuario) not in (RolUsuario.ADMINISTRADOR.value, RolUsuario.AUDITOR.value):
        consulta = consulta.filter(Documento.area_id == usuario.area_id)
    analisis_lista = consulta.order_by(Analisis.fecha_inicio.desc()).limit(limite).all()
    return [
        _a_respuesta_analisis(
            sesion, analisis, sesion.get(Documento, analisis.documento_id), usuario
        )
        for analisis in analisis_lista
    ]


@app.get("/analisis/{analisis_id}", response_model=RespuestaAnalisis)
def consultar_analisis(
    analisis_id: str,
    usuario: Annotated[Usuario, Depends(usuario_actual)],
    sesion: Annotated[Session, Depends(obtener_sesion)],
) -> RespuestaAnalisis:
    analisis, documento = _analisis_y_documento_accesibles(
        sesion, usuario, analisis_id, mensaje_403="No puede consultar análisis de otra área"
    )
    return _a_respuesta_analisis(sesion, analisis, documento, usuario)


@app.get("/analisis/{analisis_id}/hallazgos", response_model=list[HallazgoEsquema])
def listar_hallazgos(
    analisis_id: str,
    usuario: Annotated[Usuario, Depends(usuario_actual)],
    sesion: Annotated[Session, Depends(obtener_sesion)],
) -> list[HallazgoEsquema]:
    analisis, _documento = _analisis_y_documento_accesibles(
        sesion, usuario, analisis_id, mensaje_403="No puede consultar hallazgos de otra área"
    )
    hallazgos = sesion.query(Hallazgo).filter_by(analisis_id=analisis.id).all()
    return [
        HallazgoEsquema(
            id=str(h.id),
            regla_codigo=None,
            severidad=h.severidad,
            ubicacion=h.ubicacion,
            descripcion=h.descripcion,
            correccion_sugerida=h.correccion_sugerida,
            monto=float(h.monto) if h.monto is not None else None,
            moneda=h.moneda,
            estado=h.estado,
            fuente_citada=h.fuente_citada,
            referencia_citada=h.referencia_citada,
        )
        for h in hallazgos
    ]


@app.get("/analisis/{analisis_id}/bitacora", response_model=list[BitacoraEsquema])
def listar_bitacora_analisis(
    analisis_id: str,
    usuario: Annotated[Usuario, Depends(usuario_actual)],
    sesion: Annotated[Session, Depends(obtener_sesion)],
) -> list[BitacoraEsquema]:
    """Pantalla "Agente trabajando" (U3): registro de pasos del análisis.
    Hoy solo hay 'analisis_iniciado'/'analisis_completado' (ver
    orquestador/tareas.py) — el pipeline no emite eventos más granulares
    todavía."""
    analisis, _documento = _analisis_y_documento_accesibles(
        sesion, usuario, analisis_id, mensaje_403="No puede consultar la bitácora de otra área"
    )
    entradas = (
        sesion.query(Bitacora)
        .filter_by(entidad_tipo="analisis", entidad_id=analisis.id)
        .order_by(Bitacora.fecha_hora)
        .all()
    )
    return [
        BitacoraEsquema(id=str(e.id), accion=e.accion, fecha_hora=e.fecha_hora, detalle=e.detalle)
        for e in entradas
    ]


@app.post("/hallazgos/{hallazgo_id}/decision", response_model=RespuestaDecision)
def decidir_hallazgo(
    hallazgo_id: str,
    datos: SolicitudDecision,
    usuario: Annotated[
        Usuario, Depends(requiere_rol(RolUsuario.REVISOR, RolUsuario.ADMINISTRADOR))
    ],
    sesion: Annotated[Session, Depends(obtener_sesion)],
) -> RespuestaDecision:
    hallazgo = sesion.get(Hallazgo, uuid.UUID(hallazgo_id))
    if hallazgo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hallazgo no encontrado")

    analisis = sesion.get(Analisis, hallazgo.analisis_id)
    documento = sesion.get(Documento, analisis.documento_id) if analisis else None

    # RN-07 / RNF-02: quien cargó el documento no puede decidir sobre sus propios
    # hallazgos, ni siquiera si tiene rol Administrador.
    if documento is not None and documento.usuario_carga_id == usuario.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Quien cargó el documento no puede decidir sobre sus propios hallazgos "
            "(segregación de funciones, RN-07)",
        )

    if datos.resultado not in ("aceptado", "rechazado", "deshecho"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="resultado debe ser 'aceptado', 'rechazado' o 'deshecho'",
        )

    decision = Decision(
        hallazgo_id=hallazgo.id,
        usuario_id=usuario.id,
        resultado=datos.resultado,
        comentario=datos.comentario,
        fecha=datetime.now(UTC),
    )
    hallazgo.estado = datos.resultado
    sesion.add(decision)
    sesion.add(
        Bitacora(
            usuario_id=usuario.id,
            accion=f"hallazgo_{datos.resultado}",
            entidad_tipo="hallazgo",
            entidad_id=hallazgo.id,
            fecha_hora=datetime.now(UTC),
            detalle=datos.comentario,
        )
    )
    sesion.commit()

    return RespuestaDecision(
        id=str(decision.id),
        hallazgo_id=str(hallazgo.id),
        resultado=decision.resultado,
        fecha=decision.fecha,
    )


@app.post("/analisis/{analisis_id}/generar-corregido", response_model=RespuestaGenerarCorregido)
def generar_corregido(
    analisis_id: str,
    usuario: Annotated[
        Usuario, Depends(requiere_rol(RolUsuario.REVISOR, RolUsuario.ADMINISTRADOR))
    ],
    sesion: Annotated[Session, Depends(obtener_sesion)],
    cliente_s3: Annotated[object, Depends(obtener_cliente_almacenamiento)],
) -> RespuestaGenerarCorregido:
    """RF-14 (CU-05): aplica solo los hallazgos ya "aceptados" (CU-07) sobre
    el documento original y sube el resultado como nueva `VersionDocumento`
    corregida. A diferencia de CU-01, esto no ocurre automáticamente durante
    el análisis -- el Revisor lo dispara explícitamente después de decidir
    (docs/03-diseno/secuencia/cu-05-ortografia.md, supuesto 4). Sin LLM de
    por medio (las correcciones ya están decididas), se hace síncrono."""
    analisis = sesion.get(Analisis, uuid.UUID(analisis_id))
    if analisis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Análisis no encontrado")
    documento = sesion.get(Documento, analisis.documento_id)
    if documento is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento no encontrado")

    if documento.usuario_carga_id == usuario.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Quien cargó el documento no puede generar el corregido (RN-07)",
        )
    if _nombre_rol(usuario) not in (RolUsuario.ADMINISTRADOR.value, RolUsuario.AUDITOR.value):
        if documento.area_id != usuario.area_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No puede generar el corregido de un análisis de otra área",
            )

    tipo_revision = sesion.get(TipoRevision, analisis.tipo_revision_id)
    if tipo_revision is None or tipo_revision.nombre != "ortografia":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo aplica a análisis de tipo 'ortografia'",
        )

    hallazgos = sesion.query(Hallazgo).filter_by(analisis_id=analisis.id).all()
    version_original = (
        sesion.query(VersionDocumento)
        .filter_by(documento_id=documento.id, es_corregida=False)
        .order_by(VersionDocumento.numero_version.asc())
        .first()
    )
    if version_original is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No se encontró el documento original"
        )

    contenido_original = almacenamiento.descargar_objeto(
        cliente_s3, BUCKET_DOCUMENTOS, version_original.ruta_almacenamiento
    )
    resultado = generar_documento_corregido(
        tipo_archivo=documento.tipo_archivo,
        contenido_original=contenido_original,
        hallazgos=hallazgos,
    )
    if resultado is None:
        return RespuestaGenerarCorregido(generado=False)

    contenido_corregido, extension = resultado
    ultima_version = (
        max(v.numero_version for v in documento.versiones) if documento.versiones else 1
    )
    base, _, _ = version_original.ruta_almacenamiento.rpartition(".")
    llave_corregida = f"{base}.corregido.{extension}"
    almacenamiento.subir_objeto(cliente_s3, BUCKET_DOCUMENTOS, llave_corregida, contenido_corregido)
    sesion.add(
        VersionDocumento(
            documento_id=documento.id,
            numero_version=ultima_version + 1,
            ruta_almacenamiento=llave_corregida,
            es_corregida=True,
            fecha_creacion=datetime.now(UTC),
        )
    )
    sesion.commit()
    return RespuestaGenerarCorregido(generado=True)


@app.get("/fuentes-conocimiento", response_model=list[FuenteConocimientoEsquema])
def listar_fuentes_conocimiento(
    usuario: Annotated[Usuario, Depends(usuario_actual)],
    sesion: Annotated[Session, Depends(obtener_sesion)],
) -> list[FuenteConocimientoEsquema]:
    """RF-16: fuentes vigentes del área del usuario, para que elija cuáles
    consultar al iniciar un análisis (ver ADR-002, estado=vigente)."""
    fuentes = (
        sesion.query(FuenteConocimiento)
        .filter_by(area_id=usuario.area_id, estado="vigente")
        .order_by(FuenteConocimiento.titulo)
        .all()
    )
    return [
        FuenteConocimientoEsquema(
            id=str(f.id),
            fuente_id=f.fuente_id,
            titulo=f.titulo,
            tipo=f.tipo,
            version=f.version,
            vigente_desde=f.vigente_desde,
        )
        for f in fuentes
    ]


@app.get("/documentos/{documento_id}/version-corregida")
def descargar_version_corregida(
    documento_id: str,
    usuario: Annotated[Usuario, Depends(usuario_actual)],
    sesion: Annotated[Session, Depends(obtener_sesion)],
    cliente_s3: Annotated[object, Depends(obtener_cliente_almacenamiento)],
) -> Response:
    """Descarga la versión corregida del documento -- el Excel con celdas
    marcadas de CU-01 (validadores.contable.salida) o el documento con el
    texto ya corregido de CU-05 (ortografia.generar_corregido). La API hace
    de intermediaria en vez de dar un enlace directo a LocalStack/MinIO
    porque ese endpoint interno (`localstack:4566`) no es alcanzable desde
    el navegador."""
    documento = sesion.get(Documento, uuid.UUID(documento_id))
    if documento is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento no encontrado")
    if _nombre_rol(usuario) not in (RolUsuario.ADMINISTRADOR.value, RolUsuario.AUDITOR.value):
        if documento.area_id != usuario.area_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No puede descargar documentos de otra área",
            )

    version = (
        sesion.query(VersionDocumento)
        .filter_by(documento_id=documento.id, es_corregida=True)
        .order_by(VersionDocumento.numero_version.desc())
        .first()
    )
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Este documento no tiene una versión corregida todavía",
        )

    contenido = almacenamiento.descargar_objeto(
        cliente_s3, BUCKET_DOCUMENTOS, version.ruta_almacenamiento
    )
    # El nombre de descarga sale de la propia llave de almacenamiento (no de
    # documento.nombre_original + una extensión fija): la extensión real del
    # corregido puede diferir de la original (CU-05, PDF -> docx).
    nombre_descarga = version.ruta_almacenamiento.rsplit("/", 1)[-1]
    tipo_mime = mimetypes.guess_type(nombre_descarga)[0] or "application/octet-stream"
    return Response(
        content=contenido,
        media_type=tipo_mime,
        headers={"Content-Disposition": f'attachment; filename="{nombre_descarga}"'},
    )


# --- Bloque K5 (RF-16, RF-19, CU-08): pantalla del curador ------------------
#
# Curador gestiona (lee y escribe) las fuentes/glosario de SU área; Administrador
# y Auditor solo pueden leer (todas las áreas) -- así lo pide el propio Bloque
# K5, más estricto que la matriz base de docs/03-diseno/seguridad/roles-
# permisos.md (que no le da a Curador ni Administrador acceso al otro lado).
# Toda escritura queda en bitácora (RF-19).


def _fuente_curaduria(sesion: Session, usuario: Usuario, fuente_id: str) -> FuenteConocimiento:
    fuente = sesion.get(FuenteConocimiento, uuid.UUID(fuente_id))
    if fuente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fuente no encontrada")
    if _nombre_rol(usuario) not in (RolUsuario.ADMINISTRADOR.value, RolUsuario.AUDITOR.value):
        if fuente.area_id != usuario.area_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No puede gestionar fuentes de otra área",
            )
    return fuente


def _a_esquema_fuente(f: FuenteConocimiento) -> FuenteCuraduriaEsquema:
    return FuenteCuraduriaEsquema(
        id=str(f.id),
        fuente_id=f.fuente_id,
        titulo=f.titulo,
        tipo=f.tipo,
        prioridad=f.prioridad,
        version=f.version,
        vigente_desde=f.vigente_desde,
        estado=f.estado,
        area_id=str(f.area_id),
        dueno=f.dueno,
        archivo=f.archivo,
        sha256=f.sha256,
        cargado_por=str(f.cargado_por),
        aprobado_por=str(f.aprobado_por) if f.aprobado_por else None,
        fecha_carga=f.fecha_carga,
        fecha_aprobacion=f.fecha_aprobacion,
    )


def _bitacora_curaduria(
    sesion: Session, *, usuario: Usuario, accion: str, entidad_id: uuid.UUID, detalle: str
) -> None:
    sesion.add(
        Bitacora(
            usuario_id=usuario.id,
            accion=accion,
            entidad_tipo="fuente_conocimiento",
            entidad_id=entidad_id,
            fecha_hora=datetime.now(UTC),
            detalle=detalle,
        )
    )


_ES_HOJA_EMBEBIDA = 'hoja "'


@app.get("/curaduria/fuentes", response_model=list[FuenteCuraduriaEsquema])
def listar_fuentes_curaduria(
    usuario: Annotated[
        Usuario,
        Depends(
            requiere_rol(RolUsuario.CURADOR, RolUsuario.ADMINISTRADOR, RolUsuario.AUDITOR)
        ),
    ],
    sesion: Annotated[Session, Depends(obtener_sesion)],
) -> list[FuenteCuraduriaEsquema]:
    """Curador ve las fuentes (todas las versiones/estados) de su área;
    Administrador y Auditor, de todas las áreas -- solo lectura."""
    consulta = sesion.query(FuenteConocimiento)
    if _nombre_rol(usuario) not in (RolUsuario.ADMINISTRADOR.value, RolUsuario.AUDITOR.value):
        consulta = consulta.filter(FuenteConocimiento.area_id == usuario.area_id)
    fuentes = consulta.order_by(
        FuenteConocimiento.fuente_id, FuenteConocimiento.fecha_carga.desc()
    ).all()
    return [_a_esquema_fuente(f) for f in fuentes]


@app.post("/curaduria/fuentes", response_model=FuenteCuraduriaEsquema)
async def crear_fuente(
    usuario: Annotated[Usuario, Depends(requiere_rol(RolUsuario.CURADOR))],
    sesion: Annotated[Session, Depends(obtener_sesion)],
    cliente_s3: Annotated[object, Depends(obtener_cliente_almacenamiento)],
    fuente_id: Annotated[str, Form()],
    titulo: Annotated[str, Form()],
    tipo: Annotated[str, Form()],
    version: Annotated[str, Form()],
    vigente_desde: Annotated[date, Form()],
    dueno: Annotated[str, Form()],
    archivo: Annotated[UploadFile, File()],
) -> FuenteCuraduriaEsquema:
    """Registra una fuente nueva (o una nueva versión de una existente,
    mismo fuente_id) como "borrador" -- nunca queda vigente hasta que el
    propio curador la aprueba (POST .../aprobar)."""
    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El archivo está vacío"
        )

    tipo_clasificado = clasificar_tipo_fuente(tipo)
    nombre_archivo = archivo.filename or "archivo"
    llave = f"{usuario.area_id}/{fuente_id}/{version}/{nombre_archivo}"
    almacenamiento.subir_objeto(cliente_s3, BUCKET_CONOCIMIENTO, llave, contenido)

    fila = FuenteConocimiento(
        fuente_id=fuente_id,
        titulo=titulo,
        tipo=tipo_clasificado,
        prioridad=prioridad_de_tipo(tipo_clasificado),
        version=version,
        vigente_desde=vigente_desde,
        estado="borrador",
        area_id=usuario.area_id,
        dueno=dueno,
        archivo=llave,
        sha256=hashlib.sha256(contenido).hexdigest(),
        cargado_por=usuario.id,
        fecha_carga=datetime.now(UTC),
    )
    sesion.add(fila)
    sesion.flush()
    _bitacora_curaduria(
        sesion,
        usuario=usuario,
        accion="fuente_cargada",
        entidad_id=fila.id,
        detalle=f"{fuente_id} v{version} (borrador)",
    )
    sesion.commit()
    return _a_esquema_fuente(fila)


@app.get("/curaduria/fuentes/{fuente_id}/vista-previa", response_model=RespuestaVistaPrevia)
def vista_previa_fuente(
    fuente_id: str,
    usuario: Annotated[
        Usuario,
        Depends(
            requiere_rol(RolUsuario.CURADOR, RolUsuario.ADMINISTRADOR, RolUsuario.AUDITOR)
        ),
    ],
    sesion: Annotated[Session, Depends(obtener_sesion)],
    cliente_s3: Annotated[object, Depends(obtener_cliente_almacenamiento)],
) -> RespuestaVistaPrevia:
    """Extrae los fragmentos (por sección/página) del archivo YA CARGADO de
    la fuente, sin indexar nada -- para que el curador revise antes de
    aprobar. No aplica a las fuentes que vienen de una hoja de la
    plantilla (Catálogo/Glosario/Checklist): esas no tienen un archivo
    propio, ya están en tablas estructuradas."""
    fuente = _fuente_curaduria(sesion, usuario, fuente_id)
    if fuente.archivo.lower().startswith(_ES_HOJA_EMBEBIDA):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Esta fuente viene de una hoja de la plantilla; no tiene vista previa "
                "de fragmentos"
            ),
        )
    contenido = almacenamiento.descargar_objeto(cliente_s3, BUCKET_CONOCIMIENTO, fuente.archivo)
    extension = fuente.archivo.rsplit(".", 1)[-1] if "." in fuente.archivo else ""
    try:
        fragmentos = extraer_fragmentos(extension, contenido)
    except PdfSinTextoError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    return RespuestaVistaPrevia(
        fragmentos=[
            FragmentoVistaPreviaEsquema(contenido=f.contenido, seccion=f.seccion, pagina=f.pagina)
            for f in fragmentos
        ]
    )


@app.post("/curaduria/fuentes/{fuente_id}/aprobar", response_model=RespuestaAprobarFuente)
def aprobar_fuente_endpoint(
    fuente_id: str,
    usuario: Annotated[Usuario, Depends(requiere_rol(RolUsuario.CURADOR))],
    sesion: Annotated[Session, Depends(obtener_sesion)],
    cliente_s3: Annotated[object, Depends(obtener_cliente_almacenamiento)],
    cliente_qdrant: Annotated[QdrantClient, Depends(obtener_cliente_qdrant)],
    funcion_embedding: Annotated[
        Callable[[str], list[float]], Depends(obtener_funcion_embedding)
    ],
    coleccion: Annotated[str, Depends(obtener_coleccion_kb)],
) -> RespuestaAprobarFuente:
    """Aprueba la fuente como vigente (curaduria.fuentes.aprobar_fuente --
    obsoletea automáticamente cualquier versión vigente anterior del mismo
    fuente_id) y la indexa (curaduria.indexacion.indexar_fuente: extrae,
    calcula embeddings, guarda en Qdrant, mide y registra el tiempo). Todo
    en una sola transacción: si la indexación falla (p. ej. PDF sin
    texto), la aprobación tampoco queda."""
    fuente = _fuente_curaduria(sesion, usuario, fuente_id)
    if fuente.estado != "borrador":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La fuente está en estado '{fuente.estado}', no 'borrador'",
        )
    if fuente.archivo.lower().startswith(_ES_HOJA_EMBEBIDA):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Esta fuente viene de una hoja de la plantilla; no tiene un archivo "
                "propio que indexar"
            ),
        )

    area = sesion.get(Area, fuente.area_id)
    contenido = almacenamiento.descargar_objeto(cliente_s3, BUCKET_CONOCIMIENTO, fuente.archivo)
    extension = fuente.archivo.rsplit(".", 1)[-1] if "." in fuente.archivo else ""

    anterior = aprobar_fuente(sesion, fuente, aprobado_por=usuario.id, ahora=datetime.now(UTC))
    _bitacora_curaduria(
        sesion,
        usuario=usuario,
        accion="fuente_aprobada",
        entidad_id=fuente.id,
        detalle=f"{fuente.fuente_id} v{fuente.version} -> vigente",
    )
    sesion.flush()

    # v1 y v2 comparten fuente_id de negocio (p. ej. "POL-001") --
    # desactivar_fragmentos_de_fuente filtra por ese campo, así que hay que
    # desactivar los puntos de la versión anterior ANTES de indexar los de
    # la nueva. Si se hiciera después (como antes de este fix), el filtro
    # también apagaría los puntos recién indexados de la nueva versión,
    # dejándola sin fragmentos buscables pese a estar "vigente" (RF-16/PP-08).
    if anterior is not None:
        desactivar_fragmentos_de_fuente(
            cliente_qdrant, coleccion=coleccion, fuente_id_negocio=fuente.fuente_id
        )

    try:
        resultado = indexar_fuente(
            sesion,
            cliente_qdrant,
            fuente=fuente,
            contenido_archivo=contenido,
            tipo_archivo=extension,
            area_nombre=area.nombre if area else "",
            funcion_embedding=funcion_embedding,
            dimension=DIMENSION_BGE_M3,
            usuario_id=usuario.id,
            coleccion=coleccion,
        )
    except PdfSinTextoError as error:
        sesion.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error

    return RespuestaAprobarFuente(
        fuente_id=fuente.fuente_id,
        version=fuente.version,
        fragmentos_indexados=resultado.fragmentos_indexados,
        duracion_segundos=resultado.duracion_segundos,
        version_anterior_obsoleta=anterior is not None,
    )


@app.post("/curaduria/fuentes/{fuente_id}/marcar-obsoleta", response_model=FuenteCuraduriaEsquema)
def marcar_fuente_obsoleta(
    fuente_id: str,
    usuario: Annotated[Usuario, Depends(requiere_rol(RolUsuario.CURADOR))],
    sesion: Annotated[Session, Depends(obtener_sesion)],
    cliente_qdrant: Annotated[QdrantClient, Depends(obtener_cliente_qdrant)],
    coleccion: Annotated[str, Depends(obtener_coleccion_kb)],
) -> FuenteCuraduriaEsquema:
    """Retira una fuente vigente sin reemplazarla por una versión nueva
    (a diferencia de aprobar_fuente, que obsoletea automáticamente al
    aprobar la siguiente) -- p. ej. un documento que dejó de aplicar. Sus
    fragmentos en Qdrant se desactivan (payload, no se borran -- RNF-06)."""
    fuente = _fuente_curaduria(sesion, usuario, fuente_id)
    if fuente.estado != "vigente":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La fuente está en estado '{fuente.estado}', no 'vigente'",
        )

    fuente.estado = "obsoleta"
    _bitacora_curaduria(
        sesion,
        usuario=usuario,
        accion="fuente_marcada_obsoleta",
        entidad_id=fuente.id,
        detalle=f"{fuente.fuente_id} v{fuente.version}",
    )
    sesion.commit()
    desactivar_fragmentos_de_fuente(
        cliente_qdrant, coleccion=coleccion, fuente_id_negocio=fuente.fuente_id
    )
    return _a_esquema_fuente(fuente)


@app.get("/curaduria/glosario", response_model=list[GlosarioEsquema])
def listar_glosario_curaduria(
    usuario: Annotated[
        Usuario,
        Depends(
            requiere_rol(RolUsuario.CURADOR, RolUsuario.ADMINISTRADOR, RolUsuario.AUDITOR)
        ),
    ],
    sesion: Annotated[Session, Depends(obtener_sesion)],
) -> list[GlosarioEsquema]:
    consulta = sesion.query(Glosario)
    if _nombre_rol(usuario) not in (RolUsuario.ADMINISTRADOR.value, RolUsuario.AUDITOR.value):
        consulta = consulta.filter(Glosario.area_id == usuario.area_id)
    return [
        GlosarioEsquema(
            id=str(g.id),
            termino=g.termino,
            definicion=g.definicion,
            area_id=str(g.area_id),
            fuente_id=str(g.fuente_id) if g.fuente_id else None,
            version=g.version,
            vigente_desde=g.vigente_desde,
        )
        for g in consulta.order_by(Glosario.termino).all()
    ]


@app.post("/curaduria/glosario", response_model=GlosarioEsquema)
def crear_termino_glosario(
    datos: SolicitudGlosario,
    usuario: Annotated[Usuario, Depends(requiere_rol(RolUsuario.CURADOR))],
    sesion: Annotated[Session, Depends(obtener_sesion)],
) -> GlosarioEsquema:
    fila = Glosario(area_id=usuario.area_id, termino=datos.termino, definicion=datos.definicion)
    sesion.add(fila)
    sesion.flush()
    sesion.add(
        Bitacora(
            usuario_id=usuario.id,
            accion="glosario_creado",
            entidad_tipo="glosario",
            entidad_id=fila.id,
            fecha_hora=datetime.now(UTC),
            detalle=datos.termino,
        )
    )
    sesion.commit()
    return GlosarioEsquema(
        id=str(fila.id),
        termino=fila.termino,
        definicion=fila.definicion,
        area_id=str(fila.area_id),
        fuente_id=None,
        version=None,
        vigente_desde=None,
    )


@app.delete("/curaduria/glosario/{termino_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_termino_glosario(
    termino_id: str,
    usuario: Annotated[Usuario, Depends(requiere_rol(RolUsuario.CURADOR))],
    sesion: Annotated[Session, Depends(obtener_sesion)],
) -> Response:
    fila = sesion.get(Glosario, uuid.UUID(termino_id))
    if fila is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Término no encontrado")
    if fila.area_id != usuario.area_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="No puede editar el glosario de otra área"
        )
    sesion.add(
        Bitacora(
            usuario_id=usuario.id,
            accion="glosario_eliminado",
            entidad_tipo="glosario",
            entidad_id=fila.id,
            fecha_hora=datetime.now(UTC),
            detalle=fila.termino,
        )
    )
    sesion.delete(fila)
    sesion.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _resumen_por_hoja(resultado: ResultadoImportacion) -> dict[str, int]:
    return {
        "fuentes": len(resultado.fuentes),
        "cuentas": len(resultado.cuentas),
        "reglas": len(resultado.reglas),
        "glosario": len(resultado.glosario),
        "checklist": len(resultado.checklist),
    }


def _errores_a_esquema(resultado: ResultadoImportacion) -> list[ErrorImportacionEsquema]:
    return [
        ErrorImportacionEsquema(hoja=e.hoja, fila=e.fila, columna=e.columna, mensaje=e.mensaje)
        for e in resultado.errores
    ]


@app.post("/curaduria/plantilla/validar", response_model=RespuestaValidarPlantilla)
async def validar_plantilla_endpoint(
    usuario: Annotated[Usuario, Depends(requiere_rol(RolUsuario.CURADOR))],
    archivo: Annotated[UploadFile, File()],
) -> RespuestaValidarPlantilla:
    """Lee y valida la plantilla SIN persistir nada (RF-16, Bloque K2/K5) --
    reporta todos los errores encontrados, de todas las hojas."""
    contenido = await archivo.read()
    resultado = leer_plantilla(contenido)
    return RespuestaValidarPlantilla(
        es_valido=resultado.es_valido,
        errores=_errores_a_esquema(resultado),
        resumen=_resumen_por_hoja(resultado),
    )


@app.post("/curaduria/plantilla/importar", response_model=RespuestaImportarPlantilla)
async def importar_plantilla_endpoint(
    usuario: Annotated[Usuario, Depends(requiere_rol(RolUsuario.CURADOR))],
    sesion: Annotated[Session, Depends(obtener_sesion)],
    archivo: Annotated[UploadFile, File()],
) -> RespuestaImportarPlantilla:
    """Valida y, si no hay ningún error, carga la plantilla completa como
    "borrador" (curaduria.plantilla.cargar_plantilla) -- nunca carga nada
    parcial: si hay errores, no se persiste nada y se devuelve el reporte."""
    contenido = await archivo.read()
    resultado = leer_plantilla(contenido)
    if not resultado.es_valido:
        return RespuestaImportarPlantilla(
            es_valido=False, errores=_errores_a_esquema(resultado), cargado=None
        )

    resumen = cargar_plantilla(
        sesion,
        resultado,
        area_id_por_defecto=usuario.area_id,
        cargado_por=usuario.id,
        ahora=datetime.now(UTC),
        contenido_plantilla=contenido,
    )
    # entidad_id sintético (uuid nuevo): la importación crea/actualiza varias
    # filas a la vez, no hay una sola entidad natural a la que anclar el
    # registro de bitácora de este evento puntual.
    _bitacora_curaduria(
        sesion,
        usuario=usuario,
        accion="plantilla_importada",
        entidad_id=uuid.uuid4(),
        detalle=(
            f"{resumen['fuentes']} fuentes, {resumen['cuentas']} cuentas, "
            f"{resumen['reglas']} reglas, {resumen['glosario']} glosario, "
            f"{resumen['checklist']} checklist"
        ),
    )
    sesion.commit()
    return RespuestaImportarPlantilla(es_valido=True, errores=[], cargado=resumen)
