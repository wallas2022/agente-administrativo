"""P-13 (Bloque 3): endpoints GET /admin/dashboard/* -- permiso dashboard:ver
(solo Administrador), y que cada uno devuelva datos reales/consistentes a
través de la API completa (no solo la lógica de comun.dashboard, ya
probada aparte en test_dashboard.py).
"""

import os
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("API_SECRET_KEY", "clave-de-prueba")

from api import main  # noqa: E402
from comun.modelos import Area, UsoLlm, Usuario  # noqa: E402


@pytest.fixture()
def cliente(sesion_bd):
    main.app.dependency_overrides[main.obtener_sesion] = lambda: sesion_bd
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


def _token(cliente: TestClient, email: str, password: str = "cambiar123") -> str:
    respuesta = cliente.post("/auth/login", json={"email": email, "password": password})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["access_token"]


def _admin(cliente: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(cliente, 'administrador@local')}"}


RUTAS_DASHBOARD = [
    "/admin/dashboard/consumo",
    "/admin/dashboard/usuarios",
    "/admin/dashboard/recursos",
    "/admin/dashboard/configuracion",
]


@pytest.mark.parametrize("ruta", RUTAS_DASHBOARD)
@pytest.mark.parametrize(
    "email", ["analista@local", "revisor@local", "curador@local", "auditor@local"]
)
def test_dashboard_rechaza_roles_sin_el_permiso(cliente: TestClient, ruta: str, email: str) -> None:
    token = _token(cliente, email)
    respuesta = cliente.get(ruta, headers={"Authorization": f"Bearer {token}"})
    assert respuesta.status_code == 403


@pytest.mark.parametrize("ruta", RUTAS_DASHBOARD)
def test_dashboard_permite_administrador(cliente: TestClient, ruta: str) -> None:
    respuesta = cliente.get(ruta, headers=_admin(cliente))
    assert respuesta.status_code == 200


def _agregar_uso(sesion_bd, *, usuario: Usuario, area: Area) -> None:
    sesion_bd.add(
        UsoLlm(
            usuario_id=usuario.id,
            area_id=area.id,
            analisis_id=None,
            caso_uso="contable",
            modelo="gpt-oss:20b",
            fecha_hora=datetime.now(UTC),
            tokens_entrada=100,
            tokens_salida=50,
            duracion_total_ms=2000,
            duracion_carga_ms=None,
            duracion_lectura_ms=None,
            duracion_generacion_ms=1500,
            resultado="ok",
        )
    )
    sesion_bd.commit()


def test_dashboard_consumo_trae_los_datos_reales(cliente: TestClient, sesion_bd) -> None:
    analista = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    area = sesion_bd.query(Area).filter_by(nombre="Contabilidad").one()
    _agregar_uso(sesion_bd, usuario=analista, area=area)

    respuesta = cliente.get("/admin/dashboard/consumo", headers=_admin(cliente))
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["tarjetas"]["llamadas"] == 1
    assert cuerpo["tarjetas"]["tokens_entrada"] == 100
    assert len(cuerpo["ranking_caso_uso"]) == 1
    assert cuerpo["ranking_caso_uso"][0]["caso_uso"] == "contable"


def test_dashboard_consumo_filtra_por_area_id(cliente: TestClient, sesion_bd) -> None:
    analista = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    area = sesion_bd.query(Area).filter_by(nombre="Contabilidad").one()
    otra_area = Area(nombre="Tesorería")
    sesion_bd.add(otra_area)
    sesion_bd.commit()
    _agregar_uso(sesion_bd, usuario=analista, area=area)

    respuesta = cliente.get(
        "/admin/dashboard/consumo",
        headers=_admin(cliente),
        params={"area_id": str(otra_area.id)},
    )
    assert respuesta.json()["tarjetas"]["llamadas"] == 0


def test_dashboard_usuarios_json(cliente: TestClient, sesion_bd) -> None:
    analista = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    area = sesion_bd.query(Area).filter_by(nombre="Contabilidad").one()
    _agregar_uso(sesion_bd, usuario=analista, area=area)

    respuesta = cliente.get("/admin/dashboard/usuarios", headers=_admin(cliente))
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert len(cuerpo) == 1
    assert cuerpo[0]["usuario_email"] == "analista@local"
    assert cuerpo[0]["tokens_entrada"] == 100


def test_dashboard_usuarios_exporta_csv(cliente: TestClient, sesion_bd) -> None:
    analista = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    area = sesion_bd.query(Area).filter_by(nombre="Contabilidad").one()
    _agregar_uso(sesion_bd, usuario=analista, area=area)

    respuesta = cliente.get(
        "/admin/dashboard/usuarios", headers=_admin(cliente), params={"formato": "csv"}
    )
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("text/csv")
    assert "analista@local" in respuesta.text
    assert "attachment" in respuesta.headers["content-disposition"]


def test_dashboard_recursos_sin_prometheus_ni_ollama_no_rompe(
    cliente: TestClient, monkeypatch
) -> None:
    """Prometheus está apagado por defecto en local (perfil "observabilidad",
    ADR-009) -- la pantalla de Recursos debe seguir respondiendo 200."""

    def _get_que_falla(url, **kwargs):
        raise httpx.ConnectError("no se pudo conectar")

    monkeypatch.setattr(httpx, "get", _get_que_falla)

    respuesta = cliente.get("/admin/dashboard/recursos", headers=_admin(cliente))
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["prometheus_disponible"] is False
    assert cuerpo["host"] is None
    assert cuerpo["ollama"] is None
    assert cuerpo["alertas"] == []


def test_dashboard_configuracion_nunca_expone_un_secreto(
    cliente: TestClient, monkeypatch
) -> None:
    monkeypatch.setenv("API_SECRET_KEY", "no-deberia-verse-nunca")
    monkeypatch.setenv("POSTGRES_PASSWORD", "tampoco-esto")

    respuesta = cliente.get("/admin/dashboard/configuracion", headers=_admin(cliente))
    assert respuesta.status_code == 200
    assert "no-deberia-verse-nunca" not in respuesta.text
    assert "tampoco-esto" not in respuesta.text
    assert "API_SECRET_KEY" not in respuesta.text
    assert "POSTGRES_PASSWORD" not in respuesta.text
