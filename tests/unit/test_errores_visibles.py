"""P-15 Bloque 1: errores visibles -- objeto ausente en S3 (409) y manejador
global de excepciones (JSON {error, detalle} con cabeceras CORS en 500)."""

import os
from pathlib import Path

import boto3
import httpx
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from qdrant_client import QdrantClient

os.environ.setdefault("API_SECRET_KEY", "clave-de-prueba")

from api import main  # noqa: E402
from comun.almacenamiento import ObjetoNoEncontradoError, descargar_objeto  # noqa: E402
from rag.cliente_embeddings import DIMENSION_BGE_M3  # noqa: E402

ORIGEN_UI = "http://localhost:5173"
COLECCION_PRUEBA = "kb_prueba_p15"
RUTA_PDF = (
    Path(__file__).resolve().parents[2]
    / "kb"
    / "plantillas"
    / "ejemplos"
    / "POL-001_Politica_Cierre_EJEMPLO.pdf"
)


def _embedding_falso(_texto: str) -> list[float]:
    return [0.1] * DIMENSION_BGE_M3


def _encabezados(cliente: TestClient, email: str) -> dict[str, str]:
    r = cliente.post("/auth/login", json={"email": email, "password": "cambiar123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _crear_fuente(cliente: TestClient, encabezados: dict[str, str]) -> dict:
    r = cliente.post(
        "/curaduria/fuentes",
        headers=encabezados,
        data={
            "fuente_id": "POL-001",
            "titulo": "Política de cierre contable",
            "tipo": "política (Word)",
            "version": "2026-01",
            "vigente_desde": "2026-01-15",
            "dueno": "Jefatura de Contabilidad",
        },
        files={"archivo": (RUTA_PDF.name, RUTA_PDF.read_bytes(), "application/pdf")},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_descargar_objeto_ausente_lanza_objeto_no_encontrado() -> None:
    with mock_aws():
        cliente = boto3.client("s3", region_name="us-east-1")
        cliente.create_bucket(Bucket="conocimiento")
        with pytest.raises(ObjetoNoEncontradoError):
            descargar_objeto(cliente, "conocimiento", "no-existe.pdf")


@pytest.fixture()
def api(sesion_bd):
    with mock_aws():
        cliente_s3 = boto3.client("s3", region_name="us-east-1")
        cliente_s3.create_bucket(Bucket="documentos")
        cliente_s3.create_bucket(Bucket="conocimiento")
        main.app.dependency_overrides[main.obtener_sesion] = lambda: sesion_bd
        main.app.dependency_overrides[main.obtener_cliente_almacenamiento] = lambda: cliente_s3
        main.app.dependency_overrides[main.obtener_cliente_qdrant] = lambda: QdrantClient(
            ":memory:"
        )
        main.app.dependency_overrides[main.obtener_funcion_embedding] = lambda: _embedding_falso
        main.app.dependency_overrides[main.obtener_coleccion_kb] = lambda: COLECCION_PRUEBA
        with TestClient(main.app, raise_server_exceptions=False) as cliente:
            yield cliente, cliente_s3
        main.app.dependency_overrides.clear()


def test_aprobar_con_archivo_ausente_en_almacenamiento_da_409(api) -> None:
    cliente, cliente_s3 = api
    encabezados = _encabezados(cliente, "curador@local")
    fuente = _crear_fuente(cliente, encabezados)
    llave = cliente_s3.list_objects_v2(Bucket="conocimiento")["Contents"][0]["Key"]
    cliente_s3.delete_object(Bucket="conocimiento", Key=llave)

    for ruta in ("aprobar", "vista-previa"):
        metodo = cliente.post if ruta == "aprobar" else cliente.get
        respuesta = metodo(f"/curaduria/fuentes/{fuente['id']}/{ruta}", headers=encabezados)
        assert respuesta.status_code == 409, ruta
        cuerpo = respuesta.json()
        mensaje = "El archivo de la fuente no está en el almacenamiento; súbalo de nuevo"
        assert cuerpo["detail"] == mensaje
        assert cuerpo["detalle"] == mensaje


def test_error_inesperado_da_500_json_con_cabeceras_cors(api) -> None:
    cliente, _ = api
    autorizacion = _encabezados(cliente, "curador@local")

    def _falla():
        raise RuntimeError("secreto interno que no debe filtrarse")

    main.app.dependency_overrides[main.obtener_sesion] = _falla
    respuesta = cliente.get("/curaduria/fuentes", headers={**autorizacion, "Origin": ORIGEN_UI})

    assert respuesta.status_code == 500
    cuerpo = respuesta.json()
    assert cuerpo["error"] == "error_interno"
    assert "RuntimeError" in cuerpo["detalle"]
    assert "secreto interno" not in cuerpo["detalle"]
    assert respuesta.headers["access-control-allow-origin"] == ORIGEN_UI
    assert respuesta.headers["access-control-allow-credentials"] == "true"


def test_timeout_de_httpx_da_mensaje_claro_con_cors(api) -> None:
    cliente, _ = api
    autorizacion = _encabezados(cliente, "curador@local")

    def _falla():
        raise httpx.ReadTimeout("tiempo agotado")

    main.app.dependency_overrides[main.obtener_sesion] = _falla
    respuesta = cliente.get("/curaduria/fuentes", headers={**autorizacion, "Origin": ORIGEN_UI})

    assert respuesta.status_code == 504
    cuerpo = respuesta.json()
    assert cuerpo["error"] == "servicio_modelos_tardo"
    assert "tardó demasiado" in cuerpo["detalle"]
    assert respuesta.headers["access-control-allow-origin"] == ORIGEN_UI


def test_origen_no_permitido_no_recibe_cabeceras_cors_en_500(api) -> None:
    cliente, _ = api
    autorizacion = _encabezados(cliente, "curador@local")

    def _falla():
        raise RuntimeError("x")

    main.app.dependency_overrides[main.obtener_sesion] = _falla
    respuesta = cliente.get(
        "/curaduria/fuentes", headers={**autorizacion, "Origin": "http://malo.example"}
    )

    assert respuesta.status_code == 500
    assert "access-control-allow-origin" not in respuesta.headers
