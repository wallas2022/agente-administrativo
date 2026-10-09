"""Pruebas de los endpoints nuevos de P-12 (Bloque 1): GET /auth/me,
POST /auth/cambiar-password, y el bloqueo por intentos fallidos en
POST /auth/login."""

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("API_SECRET_KEY", "clave-de-prueba")

from api import main  # noqa: E402
from comun.modelos import Usuario  # noqa: E402
from comun.seguridad import verificar_password  # noqa: E402


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


# --- GET /auth/me ------------------------------------------------------


def test_auth_me_devuelve_usuario_rol_area_y_permisos(cliente: TestClient) -> None:
    token = _token(cliente, "analista@local")
    respuesta = cliente.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["email"] == "analista@local"
    assert datos["rol"] == "analista"
    assert datos["area"] == "Contabilidad"
    assert "analisis:crear" in datos["permisos"]
    assert "usuarios:administrar" not in datos["permisos"]
    assert datos["debe_cambiar_password"] is False
    # Nunca contraseña ni hash en la respuesta (RNF-SEG-01).
    assert "password" not in datos
    assert "password_hash" not in datos


def test_auth_me_del_administrador_incluye_permisos_protegidos(cliente: TestClient) -> None:
    token = _token(cliente, "administrador@local")
    respuesta = cliente.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert respuesta.status_code == 200
    permisos = respuesta.json()["permisos"]
    assert "usuarios:administrar" in permisos
    assert "bitacora:ver" in permisos


def test_auth_me_sin_token_da_401(cliente: TestClient) -> None:
    respuesta = cliente.get("/auth/me")
    assert respuesta.status_code in (401, 403)  # HTTPBearer sin credenciales da 403


# --- POST /auth/cambiar-password ----------------------------------------


def test_cambiar_password_correcto(cliente: TestClient, sesion_bd) -> None:
    token = _token(cliente, "analista@local")
    respuesta = cliente.post(
        "/auth/cambiar-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"password_actual": "cambiar123", "password_nueva": "NuevaClave99"},
    )

    assert respuesta.status_code == 200
    assert respuesta.json() == {"cambiada": True}

    usuario = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    assert verificar_password("NuevaClave99", usuario.password_hash)
    assert usuario.debe_cambiar_password is False

    # El login viejo ya no sirve; el nuevo sí.
    assert cliente.post(
        "/auth/login", json={"email": "analista@local", "password": "cambiar123"}
    ).status_code == 401
    assert cliente.post(
        "/auth/login", json={"email": "analista@local", "password": "NuevaClave99"}
    ).status_code == 200


def test_cambiar_password_con_password_actual_incorrecta(cliente: TestClient) -> None:
    token = _token(cliente, "analista@local")
    respuesta = cliente.post(
        "/auth/cambiar-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"password_actual": "incorrecta", "password_nueva": "NuevaClave99"},
    )
    assert respuesta.status_code == 401


@pytest.mark.parametrize("password_nueva", ["corta1", "sinningundigito", "12345678901234"])
def test_cambiar_password_rechaza_contrasenas_debiles(
    cliente: TestClient, password_nueva: str
) -> None:
    token = _token(cliente, "analista@local")
    respuesta = cliente.post(
        "/auth/cambiar-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"password_actual": "cambiar123", "password_nueva": password_nueva},
    )
    assert respuesta.status_code == 422


# --- Bloqueo por intentos fallidos (HU-25) ------------------------------


def test_login_bloquea_tras_cinco_intentos_fallidos(cliente: TestClient) -> None:
    for _ in range(5):
        respuesta = cliente.post(
            "/auth/login", json={"email": "analista@local", "password": "incorrecta"}
        )
        assert respuesta.status_code == 401

    # Ni con la contraseña correcta entra mientras dure el bloqueo.
    respuesta = cliente.post(
        "/auth/login", json={"email": "analista@local", "password": "cambiar123"}
    )
    assert respuesta.status_code == 401
    assert "bloqueado" in respuesta.json()["detail"].lower()
