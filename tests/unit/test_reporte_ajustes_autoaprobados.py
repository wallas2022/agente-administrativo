"""Pruebas del reporte "Ajustes autoaprobados" (SRS v0.9, RG-06, PP-09,
CU-01): lista las decisiones sobre hallazgos contables donde quien decidió
es el mismo que cargó el documento -- filtrable por fecha y usuario,
visible solo para Administrador/Auditor ("Jefatura" se cubre con
Administrador, no existe como rol propio del sistema hoy).
"""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("API_SECRET_KEY", "clave-de-prueba")

from api import main  # noqa: E402
from comun.estados import EstadoAnalisis  # noqa: E402
from comun.modelos import Analisis, Documento, Hallazgo, TipoRevision, Usuario  # noqa: E402


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


def _crear_hallazgo(
    sesion_bd, *, usuario_carga_id, area_id, tipo_revision_nombre: str = "contable"
) -> str:
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

    tipo_revision = (
        sesion_bd.query(TipoRevision).filter_by(nombre=tipo_revision_nombre).one_or_none()
    )
    if tipo_revision is None:
        tipo_revision = TipoRevision(nombre=tipo_revision_nombre)
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

    hallazgo = Hallazgo(
        analisis_id=analisis.id,
        version_documento_id=uuid.uuid4(),
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

    return str(hallazgo.id)


def test_reporte_solo_incluye_ajustes_autoaprobados_de_cu01(
    cliente, sesion_bd, monkeypatch
) -> None:
    monkeypatch.delenv("SEGREGACION_APROBACION", raising=False)
    administrador = sesion_bd.query(Usuario).filter_by(email="administrador@local").one()
    analista = sesion_bd.query(Usuario).filter_by(email="analista@local").one()

    # 1) Autoaprobado, contable -- debe salir en el reporte.
    hallazgo_autoaprobado = _crear_hallazgo(
        sesion_bd, usuario_carga_id=administrador.id, area_id=administrador.area_id
    )
    token_administrador = _token(cliente, "administrador@local")
    respuesta = cliente.post(
        f"/hallazgos/{hallazgo_autoaprobado}/decision",
        headers={"Authorization": f"Bearer {token_administrador}"},
        json={"resultado": "aceptado", "comentario": "autoaprobado de prueba"},
    )
    assert respuesta.status_code == 200

    # 2) Decidido por otro usuario -- NO es autoaprobado, no debe salir.
    hallazgo_de_otro = _crear_hallazgo(
        sesion_bd, usuario_carga_id=analista.id, area_id=analista.area_id
    )
    token_revisor = _token(cliente, "revisor@local")
    respuesta = cliente.post(
        f"/hallazgos/{hallazgo_de_otro}/decision",
        headers={"Authorization": f"Bearer {token_revisor}"},
        json={"resultado": "aceptado"},
    )
    assert respuesta.status_code == 200

    # 3) Autoaprobado pero de un análisis NO contable -- no debe salir (el
    # reporte es "(CU-01)").
    hallazgo_ortografia = _crear_hallazgo(
        sesion_bd,
        usuario_carga_id=administrador.id,
        area_id=administrador.area_id,
        tipo_revision_nombre="ortografia",
    )
    respuesta = cliente.post(
        f"/hallazgos/{hallazgo_ortografia}/decision",
        headers={"Authorization": f"Bearer {token_administrador}"},
        json={"resultado": "aceptado"},
    )
    assert respuesta.status_code == 200

    token_auditor = _token(cliente, "auditor@local")
    respuesta = cliente.get(
        "/reportes/ajustes-autoaprobados", headers={"Authorization": f"Bearer {token_auditor}"}
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert len(cuerpo) == 1
    assert cuerpo[0]["hallazgo_id"] == hallazgo_autoaprobado
    assert cuerpo[0]["usuario_email"] == "administrador@local"
    assert cuerpo[0]["rol"] == "administrador"
    assert cuerpo[0]["resultado"] == "aceptado"
    assert cuerpo[0]["comentario"] == "autoaprobado de prueba"


def test_reporte_filtra_por_usuario_y_por_fecha(cliente, sesion_bd, monkeypatch) -> None:
    monkeypatch.delenv("SEGREGACION_APROBACION", raising=False)
    administrador = sesion_bd.query(Usuario).filter_by(email="administrador@local").one()

    hallazgo_id = _crear_hallazgo(
        sesion_bd, usuario_carga_id=administrador.id, area_id=administrador.area_id
    )
    token_administrador = _token(cliente, "administrador@local")
    cliente.post(
        f"/hallazgos/{hallazgo_id}/decision",
        headers={"Authorization": f"Bearer {token_administrador}"},
        json={"resultado": "aceptado"},
    )

    token_auditor = _token(cliente, "auditor@local")
    encabezados = {"Authorization": f"Bearer {token_auditor}"}

    # Filtro por el correo de quien sí decidió -- 1 resultado.
    respuesta = cliente.get(
        "/reportes/ajustes-autoaprobados",
        headers=encabezados,
        params={"usuario_email": "administrador"},
    )
    assert len(respuesta.json()) == 1

    # Filtro por un correo que no coincide -- 0 resultados.
    respuesta = cliente.get(
        "/reportes/ajustes-autoaprobados",
        headers=encabezados,
        params={"usuario_email": "nadie-existe"},
    )
    assert respuesta.json() == []

    # Rango de fechas que sí cubre hoy -- 1 resultado.
    hoy = datetime.now(UTC).date()
    respuesta = cliente.get(
        "/reportes/ajustes-autoaprobados",
        headers=encabezados,
        params={
            "fecha_desde": (hoy - timedelta(days=1)).isoformat(),
            "fecha_hasta": hoy.isoformat(),
        },
    )
    assert len(respuesta.json()) == 1

    # Rango de fechas en el pasado, sin cubrir hoy -- 0 resultados.
    respuesta = cliente.get(
        "/reportes/ajustes-autoaprobados",
        headers=encabezados,
        params={
            "fecha_desde": (hoy - timedelta(days=10)).isoformat(),
            "fecha_hasta": (hoy - timedelta(days=5)).isoformat(),
        },
    )
    assert respuesta.json() == []


def test_reporte_requiere_rol_administrador_o_auditor(cliente, sesion_bd) -> None:
    for email in ("analista@local", "revisor@local", "curador@local"):
        token = _token(cliente, email)
        respuesta = cliente.get(
            "/reportes/ajustes-autoaprobados", headers={"Authorization": f"Bearer {token}"}
        )
        assert respuesta.status_code == 403, email
