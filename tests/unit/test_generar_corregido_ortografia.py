"""Pruebas de API de CU-05 (Bloque O4):
- periodo_cierre deja de ser obligatorio salvo para tipo_revision="contable".
- POST /analisis/{id}/generar-corregido (RF-14): aplica solo los hallazgos
  "aceptados" y sube una nueva VersionDocumento corregida.
"""

import os
import uuid

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("API_SECRET_KEY", "clave-de-prueba")

from api import main  # noqa: E402
from comun.modelos import Hallazgo, VersionDocumento  # noqa: E402


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


def _crear_analisis_ortografia_via_api(
    cliente: TestClient, token: str, *, contenido: bytes, nombre: str = "texto.txt"
) -> tuple[str, str]:
    encabezados = {"Authorization": f"Bearer {token}"}
    respuesta = cliente.post(
        "/documentos/iniciar",
        headers=encabezados,
        json={"nombre_original": nombre, "tipo_archivo": "txt", "tamano_bytes": len(contenido)},
    )
    inicio = respuesta.json()
    documento_id, upload_id, llave = (
        inicio["documento_id"],
        inicio["upload_id"],
        inicio["llave_almacenamiento"],
    )
    respuesta = cliente.put(
        f"/documentos/{documento_id}/partes/1?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers=encabezados,
        content=contenido,
    )
    etag = respuesta.json()["etag"]
    respuesta = cliente.post(
        f"/documentos/{documento_id}/completar?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers=encabezados,
        json={
            "partes": [{"numero_parte": 1, "etag": etag}],
            "tipo_revision": "ortografia",
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    return documento_id, respuesta.json()["analisis_id"]


def test_completar_carga_ortografia_no_requiere_periodo_cierre(cliente: TestClient) -> None:
    token = _token(cliente, "analista@local")
    documento_id, analisis_id = _crear_analisis_ortografia_via_api(
        cliente, token, contenido=b"Texto de prueba"
    )
    assert documento_id and analisis_id


def test_completar_carga_contable_sin_periodo_cierre_devuelve_422(cliente: TestClient) -> None:
    token = _token(cliente, "analista@local")
    encabezados = {"Authorization": f"Bearer {token}"}
    respuesta = cliente.post(
        "/documentos/iniciar",
        headers=encabezados,
        json={"nombre_original": "cierre.xlsx", "tipo_archivo": "xlsx", "tamano_bytes": 1},
    )
    inicio = respuesta.json()
    documento_id, upload_id, llave = (
        inicio["documento_id"],
        inicio["upload_id"],
        inicio["llave_almacenamiento"],
    )
    respuesta = cliente.put(
        f"/documentos/{documento_id}/partes/1?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers=encabezados,
        content=b"x",
    )
    etag = respuesta.json()["etag"]

    respuesta = cliente.post(
        f"/documentos/{documento_id}/completar?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers=encabezados,
        json={"partes": [{"numero_parte": 1, "etag": etag}], "tipo_revision": "contable"},
    )

    assert respuesta.status_code == 422


def test_generar_corregido_aplica_solo_hallazgos_aceptados_y_sube_version(
    cliente: TestClient, sesion_bd
) -> None:
    token_analista = _token(cliente, "analista@local")
    contenido_original = b"Este procedimiento fue aprovado por la gerencia."
    documento_id, analisis_id = _crear_analisis_ortografia_via_api(
        cliente, token_analista, contenido=contenido_original
    )

    hallazgo_aceptado = Hallazgo(
        analisis_id=uuid.UUID(analisis_id),
        version_documento_id=uuid.uuid4(),
        severidad="media",
        ubicacion="Texto",
        descripcion="«aprovado»: error",
        correccion_sugerida="aprobado",
        texto_original="aprovado",
        estado="aceptado",
    )
    sesion_bd.add(hallazgo_aceptado)
    sesion_bd.commit()

    token_revisor = _token(cliente, "revisor@local")
    respuesta = cliente.post(
        f"/analisis/{analisis_id}/generar-corregido",
        headers={"Authorization": f"Bearer {token_revisor}"},
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["generado"] is True

    versiones = sesion_bd.query(VersionDocumento).filter_by(
        documento_id=uuid.UUID(documento_id), es_corregida=True
    ).all()
    assert len(versiones) == 1

    respuesta_descarga = cliente.get(
        f"/documentos/{documento_id}/version-corregida",
        headers={"Authorization": f"Bearer {token_revisor}"},
    )
    assert respuesta_descarga.status_code == 200
    assert b"aprobado" in respuesta_descarga.content
    assert b"aprovado" not in respuesta_descarga.content


def test_generar_corregido_sin_hallazgos_aceptados_no_genera_version(
    cliente: TestClient, sesion_bd
) -> None:
    token_analista = _token(cliente, "analista@local")
    _documento_id, analisis_id = _crear_analisis_ortografia_via_api(
        cliente, token_analista, contenido=b"Todo correcto aqui."
    )

    token_revisor = _token(cliente, "revisor@local")
    respuesta = cliente.post(
        f"/analisis/{analisis_id}/generar-corregido",
        headers={"Authorization": f"Bearer {token_revisor}"},
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["generado"] is False
    assert sesion_bd.query(VersionDocumento).filter_by(es_corregida=True).count() == 0


def test_generar_corregido_rechaza_analisis_que_no_es_ortografia(cliente: TestClient) -> None:
    token_analista = _token(cliente, "analista@local")
    encabezados = {"Authorization": f"Bearer {token_analista}"}
    respuesta = cliente.post(
        "/documentos/iniciar",
        headers=encabezados,
        json={"nombre_original": "cierre.xlsx", "tipo_archivo": "xlsx", "tamano_bytes": 1},
    )
    inicio = respuesta.json()
    documento_id, upload_id, llave = (
        inicio["documento_id"],
        inicio["upload_id"],
        inicio["llave_almacenamiento"],
    )
    respuesta = cliente.put(
        f"/documentos/{documento_id}/partes/1?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers=encabezados,
        content=b"x",
    )
    etag = respuesta.json()["etag"]
    respuesta = cliente.post(
        f"/documentos/{documento_id}/completar?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers=encabezados,
        json={
            "partes": [{"numero_parte": 1, "etag": etag}],
            "tipo_revision": "contable",
            "periodo_cierre": "2026-01",
        },
    )
    analisis_id = respuesta.json()["analisis_id"]

    token_revisor = _token(cliente, "revisor@local")
    respuesta = cliente.post(
        f"/analisis/{analisis_id}/generar-corregido",
        headers={"Authorization": f"Bearer {token_revisor}"},
    )

    assert respuesta.status_code == 400


def test_generar_corregido_rn07_quien_cargo_no_puede_aunque_sea_administrador(
    cliente: TestClient, sesion_bd
) -> None:
    token_administrador = _token(cliente, "administrador@local")
    _documento_id, analisis_id = _crear_analisis_ortografia_via_api(
        cliente, token_administrador, contenido=b"Texto de prueba"
    )

    respuesta = cliente.post(
        f"/analisis/{analisis_id}/generar-corregido",
        headers={"Authorization": f"Bearer {token_administrador}"},
    )

    assert respuesta.status_code == 403
