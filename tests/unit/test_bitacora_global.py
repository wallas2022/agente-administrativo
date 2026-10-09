"""Pruebas de GET /bitacora (P-12, Bloque 2, HU-20): auditoría global de
solo lectura para Administrador/Auditor, filtrable por fecha, usuario y
acción -- distinta de GET /analisis/{id}/bitacora (detalle de pasos de un
análisis puntual, ver roles-permisos.md v0.3).
"""

import os
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("API_SECRET_KEY", "clave-de-prueba")

from api import main  # noqa: E402


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


def _cambiar_password(cliente: TestClient, email: str, password_nueva: str) -> None:
    token = _token(cliente, email)
    respuesta = cliente.post(
        "/auth/cambiar-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"password_actual": "cambiar123", "password_nueva": password_nueva},
    )
    assert respuesta.status_code == 200, respuesta.text


@pytest.mark.parametrize("email", ["analista@local", "revisor@local", "curador@local"])
def test_bitacora_rechaza_roles_sin_el_permiso(cliente: TestClient, email: str) -> None:
    token = _token(cliente, email)
    respuesta = cliente.get("/bitacora", headers={"Authorization": f"Bearer {token}"})
    assert respuesta.status_code == 403


@pytest.mark.parametrize("email", ["administrador@local", "auditor@local"])
def test_bitacora_permite_administrador_y_auditor(cliente: TestClient, email: str) -> None:
    token = _token(cliente, email)
    respuesta = cliente.get("/bitacora", headers={"Authorization": f"Bearer {token}"})
    assert respuesta.status_code == 200


def test_bitacora_incluye_cambio_de_password_sin_exponer_hash(cliente: TestClient) -> None:
    _cambiar_password(cliente, "analista@local", "NuevaClave99")

    token_auditor = _token(cliente, "auditor@local")
    respuesta = cliente.get("/bitacora", headers={"Authorization": f"Bearer {token_auditor}"})
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()

    entradas = [e for e in cuerpo if e["accion"] == "usuario_cambio_password"]
    assert len(entradas) == 1
    assert entradas[0]["usuario_email"] == "analista@local"
    assert "password" not in entradas[0]
    assert "hash" not in entradas[0]
    assert "NuevaClave99" not in respuesta.text


def test_bitacora_filtra_por_usuario_accion_y_fecha(cliente: TestClient) -> None:
    _cambiar_password(cliente, "analista@local", "NuevaClave99")
    _cambiar_password(cliente, "revisor@local", "OtraClaveNueva1")

    token_administrador = _token(cliente, "administrador@local")
    encabezados = {"Authorization": f"Bearer {token_administrador}"}

    respuesta = cliente.get(
        "/bitacora", headers=encabezados, params={"usuario_email": "analista"}
    )
    cuerpo = respuesta.json()
    assert len(cuerpo) == 1
    assert cuerpo[0]["usuario_email"] == "analista@local"

    respuesta = cliente.get(
        "/bitacora", headers=encabezados, params={"accion": "cambio_password"}
    )
    assert len(respuesta.json()) == 2

    respuesta = cliente.get(
        "/bitacora", headers=encabezados, params={"usuario_email": "nadie-existe"}
    )
    assert respuesta.json() == []

    hoy = datetime.now(UTC).date()
    respuesta = cliente.get(
        "/bitacora",
        headers=encabezados,
        params={
            "fecha_desde": (hoy - timedelta(days=1)).isoformat(),
            "fecha_hasta": hoy.isoformat(),
        },
    )
    assert len(respuesta.json()) == 2

    respuesta = cliente.get(
        "/bitacora",
        headers=encabezados,
        params={
            "fecha_desde": (hoy - timedelta(days=10)).isoformat(),
            "fecha_hasta": (hoy - timedelta(days=5)).isoformat(),
        },
    )
    assert respuesta.json() == []
