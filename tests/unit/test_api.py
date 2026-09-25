import os
import uuid

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("API_SECRET_KEY", "clave-de-prueba")

from api import main  # noqa: E402  (después de fijar API_SECRET_KEY)
from comun.modelos import Analisis, Documento  # noqa: E402


@pytest.fixture()
def cliente(sesion_bd, cliente_s3_bucket):
    llamadas_encolar: list[tuple[str, str]] = []

    def _encolador_falso(documento_id: str, analisis_id: str) -> str:
        llamadas_encolar.append((documento_id, analisis_id))
        return "tarea-de-prueba"

    main.app.dependency_overrides[main.obtener_sesion] = lambda: sesion_bd
    main.app.dependency_overrides[main.obtener_cliente_almacenamiento] = lambda: cliente_s3_bucket
    main.app.dependency_overrides[main.obtener_encolador] = lambda: _encolador_falso

    with TestClient(main.app) as test_client:
        test_client.llamadas_encolar = llamadas_encolar  # type: ignore[attr-defined]
        yield test_client

    main.app.dependency_overrides.clear()


def _token(cliente: TestClient, email: str, password: str = "cambiar123") -> str:
    respuesta = cliente.post("/auth/login", json={"email": email, "password": password})
    assert respuesta.status_code == 200
    return respuesta.json()["access_token"]


def test_health_responde_ok(cliente: TestClient) -> None:
    respuesta = cliente.get("/health")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ok"}


def test_login_correcto_devuelve_token_y_rol(cliente: TestClient) -> None:
    respuesta = cliente.post(
        "/auth/login", json={"email": "analista@local", "password": "cambiar123"}
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["rol"] == "analista"
    assert cuerpo["access_token"]


def test_login_incorrecto_devuelve_401(cliente: TestClient) -> None:
    respuesta = cliente.post(
        "/auth/login", json={"email": "analista@local", "password": "mala"}
    )
    assert respuesta.status_code == 401


def test_iniciar_carga_requiere_autenticacion(cliente: TestClient) -> None:
    respuesta = cliente.post(
        "/documentos/iniciar",
        json={"nombre_original": "a.xlsx", "tipo_archivo": "xlsx", "tamano_bytes": 100},
    )
    assert respuesta.status_code == 403  # sin header Authorization


def test_auditor_no_puede_iniciar_carga(cliente: TestClient) -> None:
    token = _token(cliente, "auditor@local")
    respuesta = cliente.post(
        "/documentos/iniciar",
        headers={"Authorization": f"Bearer {token}"},
        json={"nombre_original": "a.xlsx", "tipo_archivo": "xlsx", "tamano_bytes": 100},
    )
    assert respuesta.status_code == 403


def test_iniciar_carga_rechaza_mas_de_1gb(cliente: TestClient) -> None:
    token = _token(cliente, "analista@local")
    respuesta = cliente.post(
        "/documentos/iniciar",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "nombre_original": "grande.xlsx",
            "tipo_archivo": "xlsx",
            "tamano_bytes": 1024 * 1024 * 1024 + 1,
        },
    )
    assert respuesta.status_code == 413


def test_flujo_completo_cu01_carga_y_consulta_de_estado(
    cliente: TestClient, sesion_bd
) -> None:
    token_analista = _token(cliente, "analista@local")
    encabezados = {"Authorization": f"Bearer {token_analista}"}

    respuesta = cliente.post(
        "/documentos/iniciar",
        headers=encabezados,
        json={"nombre_original": "cierre.xlsx", "tipo_archivo": "xlsx", "tamano_bytes": 2048},
    )
    assert respuesta.status_code == 200
    inicio = respuesta.json()
    documento_id = inicio["documento_id"]
    upload_id = inicio["upload_id"]
    llave = inicio["llave_almacenamiento"]

    respuesta = cliente.put(
        f"/documentos/{documento_id}/partes/1"
        f"?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers=encabezados,
        content=b"contenido de prueba",
    )
    assert respuesta.status_code == 200
    etag = respuesta.json()["etag"]

    respuesta = cliente.post(
        f"/documentos/{documento_id}/completar"
        f"?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers=encabezados,
        json={
            "partes": [{"numero_parte": 1, "etag": etag}],
            "tipo_revision": "contable",
            "periodo_cierre": "2026-01",
        },
    )
    assert respuesta.status_code == 200
    completado = respuesta.json()
    analisis_id = completado["analisis_id"]
    assert cliente.llamadas_encolar == [(documento_id, analisis_id)]  # type: ignore[attr-defined]

    respuesta = cliente.get(f"/analisis/{analisis_id}", headers=encabezados)
    assert respuesta.status_code == 200
    assert respuesta.json()["tipo_revision"] == "contable"

    documento = sesion_bd.get(Documento, uuid.UUID(documento_id))
    analisis = sesion_bd.get(Analisis, uuid.UUID(analisis_id))
    assert documento is not None
    assert analisis is not None
    assert documento.estado == "cargado"  # el orquestador aún no corrió (Celery está mockeado)


def test_auditor_puede_consultar_analisis_de_cualquier_area(
    cliente: TestClient, sesion_bd
) -> None:
    token_analista = _token(cliente, "analista@local")
    respuesta = cliente.post(
        "/documentos/iniciar",
        headers={"Authorization": f"Bearer {token_analista}"},
        json={"nombre_original": "a.xlsx", "tipo_archivo": "xlsx", "tamano_bytes": 100},
    )
    documento_id = respuesta.json()["documento_id"]
    upload_id = respuesta.json()["upload_id"]
    llave = respuesta.json()["llave_almacenamiento"]

    respuesta = cliente.put(
        f"/documentos/{documento_id}/partes/1?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers={"Authorization": f"Bearer {token_analista}"},
        content=b"x",
    )
    etag = respuesta.json()["etag"]

    respuesta = cliente.post(
        f"/documentos/{documento_id}/completar?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers={"Authorization": f"Bearer {token_analista}"},
        json={
            "partes": [{"numero_parte": 1, "etag": etag}],
            "tipo_revision": "contable",
            "periodo_cierre": "2026-01",
        },
    )
    analisis_id = respuesta.json()["analisis_id"]

    token_auditor = _token(cliente, "auditor@local")
    respuesta = cliente.get(
        f"/analisis/{analisis_id}", headers={"Authorization": f"Bearer {token_auditor}"}
    )
    assert respuesta.status_code == 200
