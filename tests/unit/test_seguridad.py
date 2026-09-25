import pytest
from jwt import ExpiredSignatureError

from comun.estados import RolUsuario
from comun.seguridad import (
    autenticar_usuario_local,
    crear_token_acceso,
    decodificar_token_acceso,
    obtener_usuario_de_prueba,
)


def test_usuarios_de_prueba_cubren_los_cinco_roles() -> None:
    roles = {obtener_usuario_de_prueba(f"{r.value}@local").rol for r in RolUsuario}
    assert roles == set(RolUsuario)


def test_autenticar_usuario_local_con_password_correcta() -> None:
    usuario = autenticar_usuario_local("analista@local", "cambiar123")
    assert usuario is not None
    assert usuario.rol == RolUsuario.ANALISTA


def test_autenticar_usuario_local_con_password_incorrecta_devuelve_none() -> None:
    assert autenticar_usuario_local("analista@local", "incorrecta") is None


def test_autenticar_usuario_local_inexistente_devuelve_none() -> None:
    assert autenticar_usuario_local("no-existe@local", "cambiar123") is None


def test_token_de_acceso_se_puede_crear_y_decodificar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_SECRET_KEY", "clave-de-prueba")

    token = crear_token_acceso(email="analista@local", rol=RolUsuario.ANALISTA)
    datos = decodificar_token_acceso(token)

    assert datos["email"] == "analista@local"
    assert datos["rol"] == "analista"


def test_token_expirado_lanza_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_SECRET_KEY", "clave-de-prueba")

    token = crear_token_acceso(
        email="analista@local", rol=RolUsuario.ANALISTA, minutos_expiracion=-1
    )

    with pytest.raises(ExpiredSignatureError):
        decodificar_token_acceso(token)
