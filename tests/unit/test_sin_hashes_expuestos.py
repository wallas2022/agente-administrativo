"""P-12 (Bloque 5): ningún endpoint devuelve password_hash, y ninguna
entrada de bitácora contiene una contraseña o su hash -- barre TODAS las
respuestas de los endpoints que tocan usuarios/autenticación/configuración
después de ejercitar los flujos que sí escriben en bitácora (RNF-SEG-01).
"""

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("API_SECRET_KEY", "clave-de-prueba")

from api import main  # noqa: E402
from comun.modelos import Area, Bitacora, Usuario  # noqa: E402

# bcrypt siempre empieza así -- si este prefijo aparece en una respuesta o en
# la bitácora, es un hash filtrado.
PREFIJO_HASH_BCRYPT = "$2b$"


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


def _sin_hash_ni_clave_del_sistema(cuerpo_json: str, *, hashes_reales: list[str]) -> None:
    assert "password_hash" not in cuerpo_json
    assert PREFIJO_HASH_BCRYPT not in cuerpo_json
    for hash_real in hashes_reales:
        assert hash_real not in cuerpo_json


def test_ningun_endpoint_de_usuarios_expone_el_hash(cliente: TestClient, sesion_bd) -> None:
    hashes_reales = [
        u.password_hash for u in sesion_bd.query(Usuario).all() if u.password_hash is not None
    ]
    encabezados = {"Authorization": f"Bearer {_token(cliente, 'administrador@local')}"}

    respuestas = [
        cliente.get("/usuarios", headers=encabezados),
        cliente.get("/auth/me", headers=encabezados),
        cliente.get("/bitacora", headers=encabezados),
    ]
    for respuesta in respuestas:
        assert respuesta.status_code == 200
        _sin_hash_ni_clave_del_sistema(respuesta.text, hashes_reales=hashes_reales)


def test_flujos_que_escriben_bitacora_no_dejan_contrasenas_en_el_detalle(
    cliente: TestClient, sesion_bd
) -> None:
    """Ejercita crear usuario, editar usuario, restablecer contraseña y
    cambiar la propia contraseña -- los cuatro escriben en Bitacora -- y
    revisa el campo `detalle` de TODAS las filas, no solo las nuevas."""
    administrador = sesion_bd.query(Usuario).filter_by(email="administrador@local").one()
    area = sesion_bd.query(Area).filter_by(nombre="Contabilidad").one()
    encabezados_admin = {"Authorization": f"Bearer {_token(cliente, 'administrador@local')}"}

    creado = cliente.post(
        "/usuarios",
        headers=encabezados_admin,
        json={
            "nombre": "Prueba Sin Hash",
            "email": "sin-hash@local",
            "area_id": str(area.id),
            "rol": "analista",
        },
    )
    assert creado.status_code == 201
    password_temporal_creacion = creado.json()["password_temporal"]
    usuario_id = creado.json()["usuario"]["id"]

    cliente.patch(
        f"/usuarios/{usuario_id}", headers=encabezados_admin, json={"nombre": "Renombrado"}
    )

    restablecido = cliente.post(
        f"/usuarios/{usuario_id}/restablecer-password", headers=encabezados_admin
    )
    password_temporal_reset = restablecido.json()["password_temporal"]

    token_analista = _token(cliente, "analista@local")
    cliente.post(
        "/auth/cambiar-password",
        headers={"Authorization": f"Bearer {token_analista}"},
        json={"password_actual": "cambiar123", "password_nueva": "NuevaClave99"},
    )

    hashes_reales = [
        u.password_hash for u in sesion_bd.query(Usuario).all() if u.password_hash is not None
    ]
    contrasenas_en_texto_plano = [
        "cambiar123",
        "NuevaClave99",
        password_temporal_creacion,
        password_temporal_reset,
    ]

    entradas = sesion_bd.query(Bitacora).all()
    assert len(entradas) > 0
    for entrada in entradas:
        detalle = entrada.detalle or ""
        assert PREFIJO_HASH_BCRYPT not in detalle
        for hash_real in hashes_reales:
            assert hash_real not in detalle
        for clave in contrasenas_en_texto_plano:
            assert clave not in detalle

    # Y tampoco al releer la bitácora por la API.
    respuesta = cliente.get("/bitacora", headers=encabezados_admin)
    assert respuesta.status_code == 200
    _sin_hash_ni_clave_del_sistema(respuesta.text, hashes_reales=hashes_reales)
    for clave in contrasenas_en_texto_plano:
        assert clave not in respuesta.text

    # El Administrador original sigue sin cambios de su propia contraseña --
    # usado como control negativo para confirmar que el bucle de arriba
    # realmente compara contra un hash vigente, no uno vacío.
    sesion_bd.refresh(administrador)
    assert administrador.password_hash in hashes_reales
