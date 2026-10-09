from datetime import UTC, datetime, timedelta

import pytest
from jwt import ExpiredSignatureError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from comun.modelos import Area, Base, Rol, Usuario
from comun.seguridad import (
    LIMITE_INTENTOS_FALLIDOS,
    MINUTOS_BLOQUEO,
    CredencialesInvalidasError,
    UsuarioBloqueadoError,
    autenticar_usuario,
    crear_token_acceso,
    decodificar_token_acceso,
    generar_password_temporal,
    hash_password,
    password_valida,
    verificar_password,
)


def _sesion_con_usuario(
    *, password: str = "cambiar123", activo: bool = True
) -> tuple[Session, Usuario]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sesion = Session(engine)

    area = Area(nombre="Contabilidad")
    rol = Rol(nombre="analista")
    sesion.add_all([area, rol])
    sesion.flush()

    usuario = Usuario(
        nombre="Ana Lista",
        email="analista@local",
        area_id=area.id,
        rol_id=rol.id,
        password_hash=hash_password(password),
        activo=activo,
    )
    sesion.add(usuario)
    sesion.commit()
    return sesion, usuario


# --- hash_password / verificar_password -------------------------------------


def test_hash_password_y_verificar_password() -> None:
    hash_ = hash_password("cambiar123")
    assert verificar_password("cambiar123", hash_) is True
    assert verificar_password("incorrecta", hash_) is False


# --- autenticar_usuario -------------------------------------------------


def test_autenticar_usuario_con_password_correcta() -> None:
    sesion, usuario = _sesion_con_usuario()
    resultado = autenticar_usuario(sesion, "analista@local", "cambiar123")
    assert resultado.id == usuario.id
    assert resultado.intentos_fallidos == 0
    assert resultado.ultimo_acceso is not None


def test_autenticar_usuario_inexistente_lanza_credenciales_invalidas() -> None:
    sesion, _usuario = _sesion_con_usuario()
    with pytest.raises(CredencialesInvalidasError):
        autenticar_usuario(sesion, "no-existe@local", "cambiar123")


def test_autenticar_usuario_password_incorrecta_lanza_credenciales_invalidas() -> None:
    sesion, _usuario = _sesion_con_usuario()
    with pytest.raises(CredencialesInvalidasError):
        autenticar_usuario(sesion, "analista@local", "incorrecta")


def test_autenticar_usuario_inactivo_lanza_credenciales_invalidas() -> None:
    sesion, _usuario = _sesion_con_usuario(activo=False)
    with pytest.raises(CredencialesInvalidasError):
        autenticar_usuario(sesion, "analista@local", "cambiar123")


def test_autenticar_usuario_sin_password_hash_lanza_credenciales_invalidas() -> None:
    sesion, usuario = _sesion_con_usuario()
    usuario.password_hash = None
    sesion.commit()
    with pytest.raises(CredencialesInvalidasError):
        autenticar_usuario(sesion, "analista@local", "cualquiera")


def test_intentos_fallidos_se_incrementan_y_resetean() -> None:
    sesion, usuario = _sesion_con_usuario()
    with pytest.raises(CredencialesInvalidasError):
        autenticar_usuario(sesion, "analista@local", "incorrecta")
    assert usuario.intentos_fallidos == 1

    autenticar_usuario(sesion, "analista@local", "cambiar123")
    assert usuario.intentos_fallidos == 0


def test_bloqueo_tras_cinco_intentos_fallidos() -> None:
    sesion, usuario = _sesion_con_usuario()
    for _ in range(LIMITE_INTENTOS_FALLIDOS):
        with pytest.raises(CredencialesInvalidasError):
            autenticar_usuario(sesion, "analista@local", "incorrecta")

    assert usuario.bloqueado_hasta is not None
    # Ni siquiera con la contraseña correcta se puede entrar mientras dure
    # el bloqueo (RF-01/HU-25).
    with pytest.raises(UsuarioBloqueadoError):
        autenticar_usuario(sesion, "analista@local", "cambiar123")


def test_bloqueo_expira_pasados_los_minutos(monkeypatch: pytest.MonkeyPatch) -> None:
    sesion, usuario = _sesion_con_usuario()
    usuario.intentos_fallidos = LIMITE_INTENTOS_FALLIDOS
    usuario.bloqueado_hasta = datetime.now(UTC) - timedelta(seconds=1)  # ya venció
    sesion.commit()

    resultado = autenticar_usuario(sesion, "analista@local", "cambiar123")
    assert resultado.bloqueado_hasta is None
    assert resultado.intentos_fallidos == 0
    assert MINUTOS_BLOQUEO == 15


# --- JWT: usuario_id, no email/rol -------------------------------------


def test_token_de_acceso_lleva_usuario_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_SECRET_KEY", "clave-de-prueba")
    _sesion, usuario = _sesion_con_usuario()

    token = crear_token_acceso(usuario_id=usuario.id)
    datos = decodificar_token_acceso(token)

    assert datos["sub"] == str(usuario.id)
    assert "email" not in datos
    assert "rol" not in datos


def test_token_expirado_lanza_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_SECRET_KEY", "clave-de-prueba")
    _sesion, usuario = _sesion_con_usuario()

    token = crear_token_acceso(usuario_id=usuario.id, minutos_expiracion=-1)

    with pytest.raises(ExpiredSignatureError):
        decodificar_token_acceso(token)


# --- password_valida / generar_password_temporal (P-12, Bloque 4) -------


@pytest.mark.parametrize(
    ("password", "esperado"),
    [
        ("cambiar123", True),
        ("corta1", False),  # menos de 10 caracteres
        ("sinningundigito", False),  # sin dígitos
        ("1234567890", False),  # sin letras
    ],
)
def test_password_valida(password: str, esperado: bool) -> None:
    assert password_valida(password) is esperado


def test_generar_password_temporal_siempre_es_valida() -> None:
    for _ in range(50):
        assert password_valida(generar_password_temporal())


def test_generar_password_temporal_no_repite() -> None:
    generadas = {generar_password_temporal() for _ in range(20)}
    assert len(generadas) == 20
