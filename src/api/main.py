"""API (FastAPI) — esqueleto funcional de L2.

Cubre: /health, autenticación con usuarios locales de prueba (RF-01), carga de
documentos por partes y reanudable a MinIO (RF-03, RN-09), creación de un
análisis en cola (RF-04) y consulta de su estado (RF-18). Sin validadores de
negocio todavía (Sprint 1). Relacionado con docs/03-diseno/c4/02-contenedores.md,
docs/03-diseno/secuencia/cu-01-excel-contable.md.
"""

import os
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy.orm import Session

from api.esquemas import (
    RespuestaAnalisis,
    RespuestaCompletarCarga,
    RespuestaIniciarCarga,
    RespuestaToken,
    SolicitudCompletarCarga,
    SolicitudIniciarCarga,
    SolicitudLogin,
)
from comun import almacenamiento
from comun.cola import encolar_analisis
from comun.db import obtener_sesion
from comun.estados import EstadoAnalisis, EstadoDocumento, RolUsuario
from comun.modelos import Analisis, Documento, TipoRevision, Usuario
from comun.seguridad import (
    UsuarioLocal,
    autenticar_usuario_local,
    crear_token_acceso,
    decodificar_token_acceso,
)

app = FastAPI(title="Agente Administrativo — API")

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
    )
    sesion.add(analisis)
    sesion.commit()

    encolar(str(documento.id), str(analisis.id))

    return RespuestaCompletarCarga(
        documento_id=str(documento.id), analisis_id=str(analisis.id), estado=documento.estado
    )


@app.get("/analisis/{analisis_id}", response_model=RespuestaAnalisis)
def consultar_analisis(
    analisis_id: str,
    usuario: Annotated[Usuario, Depends(usuario_actual)],
    sesion: Annotated[Session, Depends(obtener_sesion)],
) -> RespuestaAnalisis:
    analisis = sesion.get(Analisis, uuid.UUID(analisis_id))
    if analisis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Análisis no encontrado")

    documento = sesion.get(Documento, analisis.documento_id)
    if _nombre_rol(usuario) not in (RolUsuario.ADMINISTRADOR.value, RolUsuario.AUDITOR.value):
        if documento is None or documento.area_id != usuario.area_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No puede consultar análisis de otra área",
            )

    tipo_revision = sesion.get(TipoRevision, analisis.tipo_revision_id)
    return RespuestaAnalisis(
        id=str(analisis.id),
        documento_id=str(analisis.documento_id),
        tipo_revision=tipo_revision.nombre if tipo_revision else "",
        estado=documento.estado if documento else analisis.estado,
        fecha_inicio=analisis.fecha_inicio,
        fecha_fin=analisis.fecha_fin,
    )
