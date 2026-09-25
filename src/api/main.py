"""API (FastAPI) — esqueleto funcional de L2.

Cubre: /health, autenticación con usuarios locales de prueba (RF-01), carga de
documentos por partes y reanudable a MinIO (RF-03, RN-09), creación de un
análisis en cola (RF-04) y consulta de su estado (RF-18). Sin validadores de
negocio todavía (Sprint 1). Relacionado con docs/03-diseno/c4/02-contenedores.md,
docs/03-diseno/secuencia/cu-01-excel-contable.md.
"""

import os
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy.orm import Session

from api.esquemas import (
    BitacoraEsquema,
    FuenteConocimientoEsquema,
    HallazgoEsquema,
    ParteSubidaEsquema,
    RespuestaAnalisis,
    RespuestaCompletarCarga,
    RespuestaDecision,
    RespuestaIniciarCarga,
    RespuestaToken,
    SolicitudCompletarCarga,
    SolicitudDecision,
    SolicitudIniciarCarga,
    SolicitudLogin,
)
from comun import almacenamiento
from comun.cola import encolar_analisis
from comun.db import obtener_fabrica_sesion, obtener_sesion
from comun.estados import EstadoAnalisis, EstadoDocumento, RolUsuario
from comun.modelos import (
    Analisis,
    Bitacora,
    Decision,
    Documento,
    FuenteConocimiento,
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


# --- Dependencias (sobreescribibles en pruebas vía app.dependency_overrides) ---


def obtener_cliente_almacenamiento():  # pragma: no cover - override en pruebas
    return almacenamiento.obtener_cliente_s3()


def obtener_encolador() -> Callable[[str, str], str]:  # pragma: no cover - override en pruebas
    return encolar_analisis


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
        .order_by(FuenteConocimiento.nombre)
        .all()
    )
    return [
        FuenteConocimientoEsquema(
            id=str(f.id), nombre=f.nombre, version=f.version, vigente_desde=f.vigente_desde
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
    """Pantalla 3 (U4): descarga del Excel con las celdas marcadas
    (validadores.contable.salida). La API hace de intermediaria en vez de dar
    un enlace directo a LocalStack/MinIO porque ese endpoint interno
    (`localstack:4566`) no es alcanzable desde el navegador."""
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
    base, _, extension = documento.nombre_original.rpartition(".")
    nombre_descarga = f"{base or documento.nombre_original}.marcado.{extension or 'xlsx'}"
    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre_descarga}"'},
    )
