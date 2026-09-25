"""Pruebas del endpoint de decisión sobre hallazgos (RF-14, RN-07, PP-09:
segregación de funciones — quien carga el documento no puede decidir sobre
sus propios hallazgos, ni siquiera si además tiene rol Administrador).
"""

import os
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("API_SECRET_KEY", "clave-de-prueba")

from api import main  # noqa: E402
from comun.estados import EstadoAnalisis  # noqa: E402
from comun.modelos import Analisis, Decision, Documento, Hallazgo, TipoRevision  # noqa: E402


@pytest.fixture()
def cliente(sesion_bd, cliente_s3_bucket):
    def _encolador_falso(documento_id: str, analisis_id: str) -> str:
        return "tarea-de-prueba"

    main.app.dependency_overrides[main.obtener_sesion] = lambda: sesion_bd
    main.app.dependency_overrides[main.obtener_cliente_almacenamiento] = lambda: cliente_s3_bucket
    main.app.dependency_overrides[main.obtener_encolador] = lambda: _encolador_falso

    with TestClient(main.app) as test_client:
        yield test_client

    main.app.dependency_overrides.clear()


def _token(cliente: TestClient, email: str, password: str = "cambiar123") -> str:
    respuesta = cliente.post("/auth/login", json={"email": email, "password": password})
    assert respuesta.status_code == 200
    return respuesta.json()["access_token"]


def _crear_hallazgo(sesion_bd, *, usuario_carga_id, area_id) -> tuple[str, str]:
    documento = Documento(
        nombre_original="cierre.xlsx",
        tipo_archivo="xlsx",
        tamano_bytes=100,
        area_id=area_id,
        usuario_carga_id=usuario_carga_id,
        fecha_carga=datetime.now(UTC),
        fecha_expiracion=datetime.now(UTC).date(),
        estado="cargado",
    )
    sesion_bd.add(documento)
    sesion_bd.flush()

    tipo_revision = TipoRevision(nombre="contable")
    sesion_bd.add(tipo_revision)
    sesion_bd.flush()

    analisis = Analisis(
        documento_id=documento.id,
        tipo_revision_id=tipo_revision.id,
        usuario_id=usuario_carga_id,
        fecha_inicio=datetime.now(UTC),
        estado=EstadoAnalisis.COMPLETADO.value,
    )
    sesion_bd.add(analisis)
    sesion_bd.flush()

    version_documento_id = uuid.uuid4()

    hallazgo = Hallazgo(
        analisis_id=analisis.id,
        version_documento_id=version_documento_id,
        severidad="alta",
        ubicacion="Partidas!A3",
        descripcion="La cuenta '9999' no existe en el catálogo",
        correccion_sugerida="Usar una cuenta vigente del catálogo",
        monto=100.0,
        moneda="Q",
        estado="pendiente",
    )
    sesion_bd.add(hallazgo)
    sesion_bd.commit()

    return str(analisis.id), str(hallazgo.id)


def test_listar_hallazgos_devuelve_los_hallazgos_del_analisis(cliente, sesion_bd) -> None:
    token = _token(cliente, "analista@local")
    from comun.modelos import Usuario

    usuario = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    analisis_id, hallazgo_id = _crear_hallazgo(
        sesion_bd, usuario_carga_id=usuario.id, area_id=usuario.area_id
    )

    respuesta = cliente.get(
        f"/analisis/{analisis_id}/hallazgos",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert len(cuerpo) == 1
    assert cuerpo[0]["id"] == hallazgo_id
    assert cuerpo[0]["severidad"] == "alta"
    assert cuerpo[0]["ubicacion"] == "Partidas!A3"


def test_revisor_puede_aceptar_hallazgo_de_otro_usuario(cliente, sesion_bd) -> None:
    from comun.modelos import Usuario

    analista = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    _analisis_id, hallazgo_id = _crear_hallazgo(
        sesion_bd, usuario_carga_id=analista.id, area_id=analista.area_id
    )

    token_revisor = _token(cliente, "revisor@local")
    respuesta = cliente.post(
        f"/hallazgos/{hallazgo_id}/decision",
        headers={"Authorization": f"Bearer {token_revisor}"},
        json={"resultado": "aceptado", "comentario": "Corregido en el libro"},
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["resultado"] == "aceptado"
    assert cuerpo["hallazgo_id"] == hallazgo_id

    hallazgo = sesion_bd.get(Hallazgo, uuid.UUID(hallazgo_id))
    assert hallazgo.estado == "aceptado"
    decisiones = sesion_bd.query(Decision).filter_by(hallazgo_id=hallazgo.id).all()
    assert len(decisiones) == 1


def test_quien_carga_el_documento_no_puede_decidir_sobre_su_propio_hallazgo(
    cliente, sesion_bd
) -> None:
    """PP-09: segregación de funciones (RN-07). El Administrador de prueba
    también puede tener rol de revisión, pero si él mismo cargó el documento
    debe ser bloqueado igual.
    """
    from comun.modelos import Usuario

    administrador = sesion_bd.query(Usuario).filter_by(email="administrador@local").one()
    _analisis_id, hallazgo_id = _crear_hallazgo(
        sesion_bd, usuario_carga_id=administrador.id, area_id=administrador.area_id
    )

    token_administrador = _token(cliente, "administrador@local")
    respuesta = cliente.post(
        f"/hallazgos/{hallazgo_id}/decision",
        headers={"Authorization": f"Bearer {token_administrador}"},
        json={"resultado": "aceptado"},
    )
    assert respuesta.status_code == 403

    hallazgo = sesion_bd.get(Hallazgo, uuid.UUID(hallazgo_id))
    assert hallazgo.estado == "pendiente"
    assert sesion_bd.query(Decision).filter_by(hallazgo_id=hallazgo.id).count() == 0


def test_analista_no_puede_decidir_sobre_hallazgos(cliente, sesion_bd) -> None:
    from comun.modelos import Usuario

    administrador = sesion_bd.query(Usuario).filter_by(email="administrador@local").one()
    _analisis_id, hallazgo_id = _crear_hallazgo(
        sesion_bd, usuario_carga_id=administrador.id, area_id=administrador.area_id
    )

    token_analista = _token(cliente, "analista@local")
    respuesta = cliente.post(
        f"/hallazgos/{hallazgo_id}/decision",
        headers={"Authorization": f"Bearer {token_analista}"},
        json={"resultado": "aceptado"},
    )
    assert respuesta.status_code == 403


def test_decision_con_resultado_invalido_devuelve_422(cliente, sesion_bd) -> None:
    from comun.modelos import Usuario

    analista = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    _analisis_id, hallazgo_id = _crear_hallazgo(
        sesion_bd, usuario_carga_id=analista.id, area_id=analista.area_id
    )

    token_revisor = _token(cliente, "revisor@local")
    respuesta = cliente.post(
        f"/hallazgos/{hallazgo_id}/decision",
        headers={"Authorization": f"Bearer {token_revisor}"},
        json={"resultado": "aprobado_mal_escrito"},
    )
    assert respuesta.status_code == 422
