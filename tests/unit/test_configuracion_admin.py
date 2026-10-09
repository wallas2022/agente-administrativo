"""Pruebas de Configuración del Administrador (P-12, Bloque 4): Usuarios
(HU-22), Roles y permisos (HU-23), Áreas (HU-24) -- reglas de protección,
contraseña temporal mostrada una sola vez, y bitácora sin contraseñas ni
hashes.
"""

import os
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("API_SECRET_KEY", "clave-de-prueba")

from api import main  # noqa: E402
from comun.modelos import Area, Bitacora, Documento, Usuario  # noqa: E402
from comun.permisos import MATRIZ_PERMISOS_DEFECTO  # noqa: E402
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


def _admin(cliente: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(cliente, 'administrador@local')}"}


# --- Usuarios (HU-22) ----------------------------------------------------


@pytest.mark.parametrize(
    "email", ["analista@local", "revisor@local", "curador@local", "auditor@local"]
)
def test_usuarios_rechaza_roles_sin_el_permiso(cliente: TestClient, email: str) -> None:
    token = _token(cliente, email)
    assert (
        cliente.get("/usuarios", headers={"Authorization": f"Bearer {token}"}).status_code == 403
    )


def test_crear_usuario_genera_password_temporal_que_funciona(
    cliente: TestClient, sesion_bd
) -> None:
    encabezados = _admin(cliente)
    area = sesion_bd.query(Area).filter_by(nombre="Contabilidad").one()
    respuesta = cliente.post(
        "/usuarios",
        headers=encabezados,
        json={
            "nombre": "Nuevo Analista",
            "email": "nuevo-analista@local",
            "area_id": str(area.id),
            "rol": "analista",
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    password_temporal = cuerpo["password_temporal"]
    assert cuerpo["usuario"]["email"] == "nuevo-analista@local"
    assert cuerpo["usuario"]["debe_cambiar_password"] is True
    assert "password" not in cuerpo["usuario"]
    assert "password_hash" not in cuerpo["usuario"]

    # La contraseña temporal realmente sirve para entrar.
    login = cliente.post(
        "/auth/login", json={"email": "nuevo-analista@local", "password": password_temporal}
    )
    assert login.status_code == 200

    usuario_creado = sesion_bd.query(Usuario).filter_by(email="nuevo-analista@local").one()
    assert verificar_password(password_temporal, usuario_creado.password_hash)


def test_crear_usuario_rechaza_correo_duplicado(cliente: TestClient, sesion_bd) -> None:
    area = sesion_bd.query(Area).filter_by(nombre="Contabilidad").one()
    respuesta = cliente.post(
        "/usuarios",
        headers=_admin(cliente),
        json={
            "nombre": "Duplicado",
            "email": "analista@local",
            "area_id": str(area.id),
            "rol": "analista",
        },
    )
    assert respuesta.status_code == 422


def test_crear_usuario_rechaza_rol_desconocido(cliente: TestClient, sesion_bd) -> None:
    area = sesion_bd.query(Area).filter_by(nombre="Contabilidad").one()
    respuesta = cliente.post(
        "/usuarios",
        headers=_admin(cliente),
        json={
            "nombre": "Prueba",
            "email": "prueba-rol@local",
            "area_id": str(area.id),
            "rol": "super-admin",
        },
    )
    assert respuesta.status_code == 422


def test_editar_usuario_no_puede_autodesactivarse(cliente: TestClient, sesion_bd) -> None:
    administrador = sesion_bd.query(Usuario).filter_by(email="administrador@local").one()
    respuesta = cliente.patch(
        f"/usuarios/{administrador.id}", headers=_admin(cliente), json={"activo": False}
    )
    assert respuesta.status_code == 422


def test_editar_usuario_permite_desactivar_a_otro_administrador_si_queda_uno_activo(
    cliente: TestClient, sesion_bd
) -> None:
    """La regla "al menos un Administrador activo" no es "nunca tocar a un
    Administrador" -- con 2 administradores activos, desactivar a UNO
    (no a uno mismo) debe permitirse, porque sigue quedando el otro."""
    analista = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    encabezados_admin = _admin(cliente)

    cliente.patch(
        f"/usuarios/{analista.id}", headers=encabezados_admin, json={"rol": "administrador"}
    )

    # El administrador original desactiva al OTRO (recién ascendido) -- no es
    # autodesactivación, y sigue quedando el propio administrador activo.
    respuesta = cliente.patch(
        f"/usuarios/{analista.id}", headers=encabezados_admin, json={"activo": False}
    )
    assert respuesta.status_code == 200


def test_editar_usuario_rechaza_quitar_rol_al_unico_administrador_activo(
    cliente: TestClient, sesion_bd
) -> None:
    administrador = sesion_bd.query(Usuario).filter_by(email="administrador@local").one()
    encabezados = _admin(cliente)
    respuesta = cliente.patch(
        f"/usuarios/{administrador.id}", headers=encabezados, json={"rol": "analista"}
    )
    assert respuesta.status_code == 422


def test_editar_usuario_registra_bitacora_sin_datos_sensibles(
    cliente: TestClient, sesion_bd
) -> None:
    analista = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    cliente.patch(
        f"/usuarios/{analista.id}", headers=_admin(cliente), json={"nombre": "Analista Editado"}
    )
    entrada = (
        sesion_bd.query(Bitacora)
        .filter_by(entidad_tipo="usuario", entidad_id=analista.id, accion="usuario_editado")
        .one()
    )
    assert "password" not in entrada.detalle.lower()
    assert "Analista Editado" in entrada.detalle


def test_restablecer_password_genera_una_nueva_y_obliga_a_cambiarla(
    cliente: TestClient, sesion_bd
) -> None:
    analista = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    respuesta = cliente.post(
        f"/usuarios/{analista.id}/restablecer-password", headers=_admin(cliente)
    )
    assert respuesta.status_code == 200
    password_temporal = respuesta.json()["password_temporal"]

    assert (
        cliente.post(
            "/auth/login", json={"email": "analista@local", "password": "cambiar123"}
        ).status_code
        == 401
    )
    login = cliente.post(
        "/auth/login", json={"email": "analista@local", "password": password_temporal}
    )
    assert login.status_code == 200

    sesion_bd.refresh(analista)
    assert analista.debe_cambiar_password is True


# --- Roles y permisos (HU-23) ---------------------------------------------


def test_listar_permisos_trae_toda_la_matriz(cliente: TestClient) -> None:
    respuesta = cliente.get("/permisos", headers=_admin(cliente))
    assert respuesta.status_code == 200
    celdas = respuesta.json()
    total_recursos_accion = len({(c["recurso"], c["accion"]) for c in celdas})
    assert len(celdas) == 5 * total_recursos_accion


def test_otorgar_y_revocar_un_permiso_no_protegido(cliente: TestClient, sesion_bd) -> None:
    encabezados = _admin(cliente)
    # analista:conocimiento:ver no es parte de la matriz por defecto de Analista.
    respuesta = cliente.put(
        "/permisos",
        headers=encabezados,
        json={"rol": "analista", "recurso": "conocimiento", "accion": "ver", "otorgado": True},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["otorgado"] is True

    # Aplica de inmediato (HU-23): un token nuevo del analista ya lo trae.
    token_analista = _token(cliente, "analista@local")
    me = cliente.get(
        "/auth/me", headers={"Authorization": f"Bearer {token_analista}"}
    ).json()
    assert "conocimiento:ver" in me["permisos"]

    respuesta = cliente.put(
        "/permisos",
        headers=encabezados,
        json={"rol": "analista", "recurso": "conocimiento", "accion": "ver", "otorgado": False},
    )
    assert respuesta.status_code == 200
    me = cliente.get(
        "/auth/me", headers={"Authorization": f"Bearer {_token(cliente, 'analista@local')}"}
    ).json()
    assert "conocimiento:ver" not in me["permisos"]


def test_rechaza_editar_un_permiso_protegido(cliente: TestClient) -> None:
    respuesta = cliente.put(
        "/permisos",
        headers=_admin(cliente),
        json={
            "rol": "administrador",
            "recurso": "usuarios",
            "accion": "administrar",
            "otorgado": False,
        },
    )
    assert respuesta.status_code == 403


def test_rechaza_recurso_accion_desconocido(cliente: TestClient) -> None:
    respuesta = cliente.put(
        "/permisos",
        headers=_admin(cliente),
        json={"rol": "analista", "recurso": "inventado", "accion": "hacer", "otorgado": True},
    )
    assert respuesta.status_code == 422


def test_restaurar_matriz_por_defecto(cliente: TestClient, sesion_bd) -> None:
    encabezados = _admin(cliente)
    cliente.put(
        "/permisos",
        headers=encabezados,
        json={"rol": "analista", "recurso": "conocimiento", "accion": "ver", "otorgado": True},
    )
    respuesta = cliente.post("/permisos/restaurar", headers=encabezados)
    assert respuesta.status_code == 200
    total_esperado = sum(len(p) for p in MATRIZ_PERMISOS_DEFECTO.values())
    otorgados = [c for c in respuesta.json() if c["otorgado"]]
    assert len(otorgados) == total_esperado


# --- Áreas (HU-24) ---------------------------------------------------------


def test_crear_y_renombrar_area(cliente: TestClient) -> None:
    encabezados = _admin(cliente)
    respuesta = cliente.post("/areas", headers=encabezados, json={"nombre": "Tesorería"})
    assert respuesta.status_code == 201
    area_id = respuesta.json()["id"]

    respuesta = cliente.patch(
        f"/areas/{area_id}", headers=encabezados, json={"nombre": "Tesorería Corporativa"}
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == "Tesorería Corporativa"


def test_crear_area_rechaza_nombre_duplicado(cliente: TestClient) -> None:
    encabezados = _admin(cliente)
    respuesta = cliente.post("/areas", headers=encabezados, json={"nombre": "Contabilidad"})
    assert respuesta.status_code == 422
    # Insensible a mayúsculas/minúsculas.
    respuesta = cliente.post("/areas", headers=encabezados, json={"nombre": "CONTABILIDAD"})
    assert respuesta.status_code == 422


def test_no_elimina_area_con_usuarios(cliente: TestClient, sesion_bd) -> None:
    area = sesion_bd.query(Area).filter_by(nombre="Contabilidad").one()
    respuesta = cliente.delete(f"/areas/{area.id}", headers=_admin(cliente))
    assert respuesta.status_code == 409


def test_no_elimina_area_con_documentos(cliente: TestClient, sesion_bd) -> None:
    encabezados = _admin(cliente)
    area_nueva = cliente.post(
        "/areas", headers=encabezados, json={"nombre": "Área sin usuarios"}
    ).json()
    analista = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    sesion_bd.add(
        Documento(
            nombre_original="doc.xlsx",
            tipo_archivo="xlsx",
            tamano_bytes=10,
            area_id=uuid.UUID(area_nueva["id"]),
            usuario_carga_id=analista.id,
            fecha_carga=datetime.now(UTC),
            fecha_expiracion=datetime.now(UTC).date(),
            estado="cargado",
        )
    )
    sesion_bd.commit()

    respuesta = cliente.delete(f"/areas/{area_nueva['id']}", headers=encabezados)
    assert respuesta.status_code == 409


def test_elimina_area_sin_usar(cliente: TestClient) -> None:
    encabezados = _admin(cliente)
    area_nueva = cliente.post(
        "/areas", headers=encabezados, json={"nombre": "Área a borrar"}
    ).json()
    respuesta = cliente.delete(f"/areas/{area_nueva['id']}", headers=encabezados)
    assert respuesta.status_code == 204

    ids_restantes = {a["id"] for a in cliente.get("/areas", headers=encabezados).json()}
    assert area_nueva["id"] not in ids_restantes
