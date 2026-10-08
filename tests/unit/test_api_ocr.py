"""Pruebas de los endpoints de CU-06 OCR (Bloque 3): ver el original, editar
el texto reconocido y descargar el .docx resaltado."""

import os
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("API_SECRET_KEY", "clave-de-prueba")

from api import main  # noqa: E402
from comun.modelos import Bitacora, Hallazgo, VersionDocumento  # noqa: E402


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


def _crear_analisis_ocr_via_api(
    cliente: TestClient, token: str, *, contenido: bytes = b"imagen falsa"
) -> tuple[str, str]:
    encabezados = {"Authorization": f"Bearer {token}"}
    respuesta = cliente.post(
        "/documentos/iniciar",
        headers=encabezados,
        json={
            "nombre_original": "escaneo.png",
            "tipo_archivo": "png",
            "tamano_bytes": len(contenido),
        },
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
        json={"partes": [{"numero_parte": 1, "etag": etag}], "tipo_revision": "ocr"},
    )
    assert respuesta.status_code == 200, respuesta.text
    return documento_id, respuesta.json()["analisis_id"]


def _publicar_texto_ocr(sesion_bd, cliente_s3_bucket, *, documento_id: str, texto: bytes) -> str:
    llave = f"ocr/{documento_id}/texto.ocr.txt"
    cliente_s3_bucket.put_object(Bucket="documentos", Key=llave, Body=texto)
    sesion_bd.add(
        VersionDocumento(
            documento_id=uuid.UUID(documento_id),
            numero_version=2,
            ruta_almacenamiento=llave,
            es_corregida=True,
            fecha_creacion=datetime.now(UTC),
        )
    )
    sesion_bd.commit()
    return llave


# --- GET /documentos/{id}/version-original ----------------------------------


def test_descargar_version_original(cliente: TestClient) -> None:
    token = _token(cliente, "analista@local")
    documento_id, _analisis_id = _crear_analisis_ocr_via_api(
        cliente, token, contenido=b"bytes de la imagen"
    )

    respuesta = cliente.get(
        f"/documentos/{documento_id}/version-original",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert respuesta.status_code == 200
    assert respuesta.content == b"bytes de la imagen"
    assert respuesta.headers["content-type"] == "image/png"


def test_descargar_version_original_404_si_no_existe_el_documento(cliente: TestClient) -> None:
    token = _token(cliente, "analista@local")
    respuesta = cliente.get(
        f"/documentos/{uuid.uuid4()}/version-original",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert respuesta.status_code == 404


# --- PUT /documentos/{id}/texto-ocr ------------------------------------------


def test_editar_texto_ocr_sobrescribe_el_objeto_y_registra_bitacora(
    cliente: TestClient, sesion_bd, cliente_s3_bucket
) -> None:
    token = _token(cliente, "analista@local")
    documento_id, analisis_id = _crear_analisis_ocr_via_api(cliente, token)
    llave = _publicar_texto_ocr(
        sesion_bd, cliente_s3_bucket, documento_id=documento_id, texto=b"Texto original reconocido"
    )

    respuesta = cliente.put(
        f"/documentos/{documento_id}/texto-ocr",
        headers={"Authorization": f"Bearer {token}"},
        json={"texto": "Texto corregido a mano"},
    )
    assert respuesta.status_code == 200
    assert respuesta.json() == {"guardado": True}

    objeto = cliente_s3_bucket.get_object(Bucket="documentos", Key=llave)
    assert objeto["Body"].read() == b"Texto corregido a mano"

    bitacora = (
        sesion_bd.query(Bitacora).filter_by(entidad_id=uuid.UUID(analisis_id)).all()
    )
    acciones = [b.accion for b in bitacora]
    assert "ocr_edicion_manual" in acciones


def test_editar_texto_ocr_404_si_no_hay_version_de_ocr(cliente: TestClient) -> None:
    token = _token(cliente, "analista@local")
    documento_id, _analisis_id = _crear_analisis_ocr_via_api(cliente, token)

    respuesta = cliente.put(
        f"/documentos/{documento_id}/texto-ocr",
        headers={"Authorization": f"Bearer {token}"},
        json={"texto": "x"},
    )
    assert respuesta.status_code == 404


# --- GET /documentos/{id}/ocr-docx -------------------------------------------


def test_descargar_ocr_docx_resalta_palabras_dudosas(
    cliente: TestClient, sesion_bd, cliente_s3_bucket
) -> None:
    token = _token(cliente, "analista@local")
    documento_id, analisis_id = _crear_analisis_ocr_via_api(cliente, token)
    llave_texto = _publicar_texto_ocr(
        sesion_bd, cliente_s3_bucket, documento_id=documento_id, texto=b"Hola mllndo"
    )
    version_ocr = (
        sesion_bd.query(VersionDocumento).filter_by(ruta_almacenamiento=llave_texto).one()
    )
    sesion_bd.add(
        Hallazgo(
            analisis_id=uuid.UUID(analisis_id),
            version_documento_id=version_ocr.id,
            severidad="alta",
            ubicacion="Página 1",
            descripcion="Palabra reconocida con confianza dudosa (50%): «mllndo»",
            texto_original="mllndo",
            estado="pendiente",
        )
    )
    sesion_bd.commit()

    respuesta = cliente.get(
        f"/documentos/{documento_id}/ocr-docx",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert respuesta.status_code == 200
    assert (
        respuesta.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    import io

    from docx import Document
    from docx.enum.text import WD_COLOR_INDEX

    documento_docx = Document(io.BytesIO(respuesta.content))
    runs = documento_docx.paragraphs[0].runs
    dudosa = next(r for r in runs if r.text == "mllndo")
    assert dudosa.font.highlight_color == WD_COLOR_INDEX.RED

    bitacora = sesion_bd.query(Bitacora).filter_by(entidad_id=uuid.UUID(analisis_id)).all()
    assert "ocr_descarga_docx" in [b.accion for b in bitacora]


# --- bitácora de descarga del .txt (reutiliza version-corregida) -----------


def test_descargar_version_corregida_de_ocr_registra_bitacora(
    cliente: TestClient, sesion_bd, cliente_s3_bucket
) -> None:
    token = _token(cliente, "analista@local")
    documento_id, analisis_id = _crear_analisis_ocr_via_api(cliente, token)
    _publicar_texto_ocr(
        sesion_bd, cliente_s3_bucket, documento_id=documento_id, texto=b"Texto reconocido"
    )

    respuesta = cliente.get(
        f"/documentos/{documento_id}/version-corregida",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert respuesta.status_code == 200
    assert respuesta.content == b"Texto reconocido"

    bitacora = sesion_bd.query(Bitacora).filter_by(entidad_id=uuid.UUID(analisis_id)).all()
    assert "ocr_descarga_txt" in [b.accion for b in bitacora]
