"""Bloque 0 de P-12 (red de seguridad): matriz rol × endpoint con el
comportamiento ACTUAL (antes de migrar de `requiere_rol` a
`requiere_permiso`). Esta suite debe seguir en verde, sin cambiar ninguna
aserción, después de cada bloque siguiente de P-12 -- es la prueba de que
la migración no cambió ningún resultado 200/403 existente.

No prueba corrección funcional (muchos POST devuelven 404/409/422 porque el
fixture no arma el estado exacto que ese endpoint necesita) -- solo si la
autorización por rol/área deja pasar (cualquier código != 403) o bloquea
(403) a cada uno de los 5 roles.
"""

import os
from datetime import UTC, date, datetime, timedelta

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from qdrant_client import QdrantClient

os.environ.setdefault("API_SECRET_KEY", "clave-de-prueba")

from api import main  # noqa: E402
from comun.estados import EstadoAnalisis, EstadoDocumento, RolUsuario  # noqa: E402
from comun.modelos import (  # noqa: E402
    Analisis,
    Area,
    Documento,
    FuenteConocimiento,
    Glosario,
    Hallazgo,
    TipoRevision,
    Usuario,
    VersionDocumento,
)
from comun.seguridad import crear_token_acceso  # noqa: E402
from rag.cliente_embeddings import DIMENSION_BGE_M3  # noqa: E402

BUCKET_DOCUMENTOS = "documentos"
BUCKET_CONOCIMIENTO = "conocimiento"
COLECCION_PRUEBA = "kb_prueba_p12"

TODOS_LOS_ROLES = list(RolUsuario)


def _embedding_falso(_texto: str) -> list[float]:
    return [0.1] * DIMENSION_BGE_M3


def _encolador_falso(_documento_id: str, _analisis_id: str) -> str:
    return "tarea-de-prueba"


@pytest.fixture()
def cliente(sesion_bd):
    with mock_aws():
        cliente_s3 = boto3.client("s3", region_name="us-east-1")
        cliente_s3.create_bucket(Bucket=BUCKET_DOCUMENTOS)
        cliente_s3.create_bucket(Bucket=BUCKET_CONOCIMIENTO)
        cliente_qdrant = QdrantClient(":memory:")

        main.app.dependency_overrides[main.obtener_sesion] = lambda: sesion_bd
        main.app.dependency_overrides[main.obtener_cliente_almacenamiento] = lambda: cliente_s3
        main.app.dependency_overrides[main.obtener_cliente_qdrant] = lambda: cliente_qdrant
        main.app.dependency_overrides[main.obtener_funcion_embedding] = lambda: _embedding_falso
        main.app.dependency_overrides[main.obtener_coleccion_kb] = lambda: COLECCION_PRUEBA
        main.app.dependency_overrides[main.obtener_encolador] = lambda: _encolador_falso

        # raise_server_exceptions=False: a este archivo no le importa la
        # corrección funcional (el fixture no arma el contenido real de S3
        # para todos los endpoints) -- solo que la autorización deje pasar
        # (!= 403) o bloquee (403). Sin esto, un error no relacionado con
        # permisos (p. ej. NoSuchKey de S3) se propaga como excepción de
        # Python en vez de una respuesta 500, y tapa la aserción real.
        with TestClient(main.app, raise_server_exceptions=False) as test_client:
            yield test_client

        main.app.dependency_overrides.clear()


def _usuarios_sembrados(sesion) -> dict[RolUsuario, Usuario]:
    """`sesion_bd` (tests/unit/conftest.py) ya siembra 1 área "Contabilidad"
    + 5 usuarios (uno por rol, email `<rol>@local`) vía
    `comun.semillas.sembrar_datos_de_prueba` -- se reutilizan en vez de
    crear otros (el email es único, duplicarlos rompería la sesión)."""
    return {
        rol: sesion.query(Usuario).filter_by(email=f"{rol.value}@local").one()
        for rol in TODOS_LOS_ROLES
    }


class Fixture:
    """Recursos de prueba (documento, análisis, hallazgo, fuentes,
    glosario) en un área dada -- `area` puede ser la ya sembrada por
    `sesion_bd` ("Contabilidad") o una nueva, para probar segmentación."""

    def __init__(
        self, sesion, *, area: Area, usuarios: dict[RolUsuario, Usuario], sufijo: str
    ) -> None:
        self.area = area
        self.usuarios = usuarios

        tipo_revision = (
            sesion.query(TipoRevision).filter_by(nombre="contable").one_or_none()
        )
        if tipo_revision is None:
            tipo_revision = TipoRevision(nombre="contable")
            sesion.add(tipo_revision)
            sesion.flush()

        self.documento = Documento(
            nombre_original=f"cierre-{sufijo}.xlsx",
            tipo_archivo="xlsx",
            tamano_bytes=100,
            area_id=self.area.id,
            usuario_carga_id=usuarios[RolUsuario.ANALISTA].id,
            fecha_carga=datetime.now(UTC),
            fecha_expiracion=date.today() + timedelta(days=90),
            estado=EstadoDocumento.CON_HALLAZGOS.value,
        )
        sesion.add(self.documento)
        sesion.flush()

        self.version = VersionDocumento(
            documento_id=self.documento.id,
            numero_version=1,
            ruta_almacenamiento=f"{self.area.id}/{self.documento.id}/cierre.xlsx",
            es_corregida=False,
            fecha_creacion=datetime.now(UTC),
        )
        self.version_corregida = VersionDocumento(
            documento_id=self.documento.id,
            numero_version=2,
            ruta_almacenamiento=f"{self.area.id}/{self.documento.id}/cierre.ocr.txt",
            es_corregida=True,
            fecha_creacion=datetime.now(UTC),
        )
        sesion.add_all([self.version, self.version_corregida])
        sesion.flush()

        self.analisis = Analisis(
            documento_id=self.documento.id,
            tipo_revision_id=tipo_revision.id,
            usuario_id=usuarios[RolUsuario.ANALISTA].id,
            fecha_inicio=datetime.now(UTC),
            fecha_fin=datetime.now(UTC),
            estado=EstadoAnalisis.COMPLETADO.value,
        )
        sesion.add(self.analisis)
        sesion.flush()

        self.hallazgo = Hallazgo(
            analisis_id=self.analisis.id,
            version_documento_id=self.version.id,
            severidad="media",
            ubicacion="Hoja1!A1",
            descripcion="hallazgo de prueba",
            estado="pendiente",
        )
        sesion.add(self.hallazgo)

        self.fuente_borrador = FuenteConocimiento(
            fuente_id=f"POL-{sufijo}",
            titulo="Política de prueba",
            tipo="regla_interna",
            prioridad=1,
            version="v1",
            vigente_desde=date.today(),
            estado="borrador",
            area_id=self.area.id,
            dueno="Jefatura de prueba",
            archivo=f"{self.area.id}/POL-{sufijo}/v1/archivo.pdf",
            sha256="0" * 64,
            cargado_por=usuarios[RolUsuario.CURADOR].id,
            fecha_carga=datetime.now(UTC),
        )
        self.fuente_vigente = FuenteConocimiento(
            fuente_id=f"POL-VIGENTE-{sufijo}",
            titulo="Política vigente de prueba",
            tipo="regla_interna",
            prioridad=1,
            version="v1",
            vigente_desde=date.today(),
            estado="vigente",
            area_id=self.area.id,
            dueno="Jefatura de prueba",
            archivo=f"{self.area.id}/POL-VIGENTE-{sufijo}/v1/archivo.pdf",
            sha256="0" * 64,
            cargado_por=usuarios[RolUsuario.CURADOR].id,
            fecha_carga=datetime.now(UTC),
        )
        sesion.add_all([self.fuente_borrador, self.fuente_vigente])
        sesion.flush()

        self.glosario = Glosario(
            area_id=self.area.id,
            termino=f"SFC-{sufijo}",
            definicion="Servicios Financieros Compartidos",
        )
        sesion.add(self.glosario)
        sesion.commit()


@pytest.fixture()
def datos(sesion_bd) -> Fixture:
    usuarios = _usuarios_sembrados(sesion_bd)
    area = sesion_bd.query(Area).filter_by(nombre="Contabilidad").one()
    return Fixture(sesion_bd, area=area, usuarios=usuarios, sufijo="propia")


def _token(rol: RolUsuario) -> str:
    return crear_token_acceso(email=f"{rol.value}@local", rol=rol)


def _auth(rol: RolUsuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(rol)}"}


# --- Bloque 0: matriz rol x endpoint (solo-rol, sin componente de área) -----
#
# Cada caso: (nombre, método, constructor de ruta/kwargs, roles permitidos).
# "roles permitidos" es el conjunto que HOY devuelve algo != 403.


def _casos() -> list[tuple[str, str, dict, set]]:
    return [
        (
            "iniciar_carga",
            "POST",
            {
                "url": "/documentos/iniciar",
                "json": {"nombre_original": "a.xlsx", "tipo_archivo": "xlsx", "tamano_bytes": 10},
            },
            {RolUsuario.ANALISTA, RolUsuario.ADMINISTRADOR},
        ),
        (
            "subir_parte",
            "PUT",
            {"url": "__subir_parte__", "content": b"x"},
            {RolUsuario.ANALISTA, RolUsuario.ADMINISTRADOR},
        ),
        (
            "listar_partes",
            "GET",
            {"url": "__listar_partes__"},
            {RolUsuario.ANALISTA, RolUsuario.ADMINISTRADOR},
        ),
        (
            "completar_carga",
            "POST",
            {"url": "__completar_carga__", "json": {"partes": [], "tipo_revision": "contable"}},
            {RolUsuario.ANALISTA, RolUsuario.ADMINISTRADOR},
        ),
        (
            "decidir_hallazgo",
            "POST",
            {"url": "__hallazgo_decision__", "json": {"resultado": "aceptado"}},
            {RolUsuario.REVISOR, RolUsuario.ADMINISTRADOR},
        ),
        (
            "generar_corregido",
            "POST",
            {"url": "__generar_corregido__", "json": {}},
            {RolUsuario.REVISOR, RolUsuario.ADMINISTRADOR},
        ),
        (
            "reportes_autoaprobados",
            "GET",
            {"url": "/reportes/ajustes-autoaprobados"},
            {RolUsuario.ADMINISTRADOR, RolUsuario.AUDITOR},
        ),
        (
            "curaduria_listar_fuentes",
            "GET",
            {"url": "/curaduria/fuentes"},
            {RolUsuario.CURADOR, RolUsuario.ADMINISTRADOR, RolUsuario.AUDITOR},
        ),
        (
            "curaduria_crear_fuente",
            "POST",
            {"url": "__crear_fuente__"},
            {RolUsuario.CURADOR},
        ),
        (
            "curaduria_vista_previa",
            "GET",
            {"url": "__vista_previa__"},
            {RolUsuario.CURADOR, RolUsuario.ADMINISTRADOR, RolUsuario.AUDITOR},
        ),
        (
            "curaduria_aprobar_fuente",
            "POST",
            {"url": "__aprobar_fuente__"},
            {RolUsuario.CURADOR},
        ),
        (
            "curaduria_marcar_obsoleta",
            "POST",
            {"url": "__marcar_obsoleta__"},
            {RolUsuario.CURADOR},
        ),
        (
            "curaduria_listar_glosario",
            "GET",
            {"url": "/curaduria/glosario"},
            {RolUsuario.CURADOR, RolUsuario.ADMINISTRADOR, RolUsuario.AUDITOR},
        ),
        (
            "curaduria_crear_glosario",
            "POST",
            {"url": "/curaduria/glosario", "json": {"termino": "IVA", "definicion": "Impuesto"}},
            {RolUsuario.CURADOR},
        ),
        (
            "curaduria_eliminar_glosario",
            "DELETE",
            {"url": "__eliminar_glosario__"},
            {RolUsuario.CURADOR},
        ),
        (
            "curaduria_validar_plantilla",
            "POST",
            {"url": "__validar_plantilla__"},
            {RolUsuario.CURADOR},
        ),
        (
            "curaduria_importar_plantilla",
            "POST",
            {"url": "__importar_plantilla__"},
            {RolUsuario.CURADOR},
        ),
    ]


def _resolver_kwargs(nombre_url: str, datos: Fixture) -> dict:
    """Las rutas que necesitan un id del fixture o un multipart especial se
    arman acá en vez de en la tabla (que queda legible)."""
    if nombre_url == "__subir_parte__":
        return {
            "url": f"/documentos/{datos.documento.id}/partes/1"
            "?upload_id=falso&llave_almacenamiento=falsa"
        }
    if nombre_url == "__listar_partes__":
        return {
            "url": f"/documentos/{datos.documento.id}/partes"
            "?upload_id=falso&llave_almacenamiento=falsa"
        }
    if nombre_url == "__completar_carga__":
        return {
            "url": f"/documentos/{datos.documento.id}/completar"
            "?upload_id=falso&llave_almacenamiento=falsa"
        }
    if nombre_url == "__hallazgo_decision__":
        return {"url": f"/hallazgos/{datos.hallazgo.id}/decision"}
    if nombre_url == "__generar_corregido__":
        return {"url": f"/analisis/{datos.analisis.id}/generar-corregido"}
    if nombre_url == "__crear_fuente__":
        return {
            "url": "/curaduria/fuentes",
            "data": {
                "fuente_id": "POL-999",
                "titulo": "Nueva",
                "tipo": "regla_interna",
                "version": "v1",
                "vigente_desde": str(date.today()),
                "dueno": "Jefatura",
            },
            "files": {"archivo": ("a.pdf", b"contenido", "application/pdf")},
        }
    if nombre_url == "__vista_previa__":
        return {"url": f"/curaduria/fuentes/{datos.fuente_borrador.fuente_id}/vista-previa"}
    if nombre_url == "__aprobar_fuente__":
        return {"url": f"/curaduria/fuentes/{datos.fuente_borrador.fuente_id}/aprobar"}
    if nombre_url == "__marcar_obsoleta__":
        return {"url": f"/curaduria/fuentes/{datos.fuente_vigente.fuente_id}/marcar-obsoleta"}
    if nombre_url == "__eliminar_glosario__":
        return {"url": f"/curaduria/glosario/{datos.glosario.id}"}
    if nombre_url == "__validar_plantilla__":
        return {
            "url": "/curaduria/plantilla/validar",
            "files": {"archivo": ("p.xlsx", b"contenido", "application/octet-stream")},
        }
    if nombre_url == "__importar_plantilla__":
        return {
            "url": "/curaduria/plantilla/importar",
            "files": {"archivo": ("p.xlsx", b"contenido", "application/octet-stream")},
        }
    return {}


@pytest.mark.parametrize("caso", _casos(), ids=lambda c: c[0])
@pytest.mark.parametrize("rol", TODOS_LOS_ROLES, ids=lambda r: r.value)
def test_matriz_rol_endpoint(
    caso: tuple[str, str, dict, set], rol: RolUsuario, cliente: TestClient, datos: Fixture
) -> None:
    _nombre, metodo, kwargs, roles_permitidos = caso
    kwargs = dict(kwargs)
    if kwargs["url"].startswith("__"):
        kwargs.update(_resolver_kwargs(kwargs["url"], datos))

    respuesta = cliente.request(metodo, headers=_auth(rol), **kwargs)

    if rol in roles_permitidos:
        assert respuesta.status_code != 403, (
            f"{rol.value} debería poder usar {kwargs['url']} (hoy); "
            f"respuesta: {respuesta.status_code} {respuesta.text[:200]}"
        )
    else:
        assert respuesta.status_code == 403, (
            f"{rol.value} NO debería poder usar {kwargs['url']} (hoy); "
            f"respuesta: {respuesta.status_code} {respuesta.text[:200]}"
        )


# --- Endpoints de "cualquier usuario autenticado" + segmentación por área --
#
# Estos no usan requiere_rol: cualquier rol pasa el Depends, pero el cuerpo
# del endpoint compara el área del recurso contra la del usuario (salvo
# ADMINISTRADOR/AUDITOR, que ven todas las áreas). Se prueban por separado
# porque el resultado depende de DOS cosas (rol + área), no solo del rol.


def _casos_por_area() -> list[tuple[str, str, str]]:
    """(nombre, método, plantilla de ruta con {documento_id}/{analisis_id})."""
    return [
        ("consultar_analisis", "GET", "/analisis/{analisis_id}"),
        ("listar_hallazgos", "GET", "/analisis/{analisis_id}/hallazgos"),
        ("listar_bitacora_analisis", "GET", "/analisis/{analisis_id}/bitacora"),
        ("version_corregida", "GET", "/documentos/{documento_id}/version-corregida"),
        ("version_original", "GET", "/documentos/{documento_id}/version-original"),
        ("ocr_docx", "GET", "/documentos/{documento_id}/ocr-docx"),
    ]


@pytest.fixture()
def datos_dos_areas(sesion_bd):
    usuarios = _usuarios_sembrados(sesion_bd)
    area_propia = sesion_bd.query(Area).filter_by(nombre="Contabilidad").one()
    propia = Fixture(sesion_bd, area=area_propia, usuarios=usuarios, sufijo="propia")

    area_ajena = Area(nombre="Tesoreria")
    sesion_bd.add(area_ajena)
    sesion_bd.flush()
    ajena = Fixture(sesion_bd, area=area_ajena, usuarios=usuarios, sufijo="ajena")

    return propia, ajena


@pytest.mark.parametrize("caso", _casos_por_area(), ids=lambda c: c[0])
@pytest.mark.parametrize("rol", TODOS_LOS_ROLES, ids=lambda r: r.value)
def test_matriz_area_endpoint(
    caso: tuple[str, str, str], rol: RolUsuario, cliente: TestClient, datos_dos_areas
) -> None:
    _nombre, metodo, plantilla = caso
    _propia, ajena = datos_dos_areas
    url = plantilla.format(documento_id=ajena.documento.id, analisis_id=ajena.analisis.id)

    # El usuario de `rol` vive en el área "propia"; el recurso es de "ajena".
    respuesta = cliente.request(metodo, url, headers=_auth(rol))

    if rol in (RolUsuario.ADMINISTRADOR, RolUsuario.AUDITOR):
        assert respuesta.status_code != 403, (
            f"{rol.value} ve todas las áreas; respuesta: {respuesta.status_code}"
        )
    else:
        assert respuesta.status_code == 403, (
            f"{rol.value} no debería ver el área ajena; respuesta: {respuesta.status_code}"
        )


def test_fuentes_conocimiento_filtra_por_area_sin_excepcion_de_rol(
    cliente: TestClient, datos_dos_areas
) -> None:
    """Caso especial encontrado en el diagnóstico (P-12): a diferencia de
    todos los demás endpoints, `/fuentes-conocimiento` filtra siempre por
    `usuario.area_id`, incluso para ADMINISTRADOR/AUDITOR -- nunca da 403,
    da lista vacía. Se deja como prueba explícita para no perder este
    comportamiento de vista si alguien lo "corrige" sin darse cuenta."""
    for rol in TODOS_LOS_ROLES:
        respuesta = cliente.get("/fuentes-conocimiento", headers=_auth(rol))
        assert respuesta.status_code == 200
