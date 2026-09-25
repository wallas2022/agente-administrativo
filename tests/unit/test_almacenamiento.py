import boto3
import pytest
from moto import mock_aws

from comun.almacenamiento import (
    TAMANO_MAXIMO_BYTES,
    ArchivoDemasiadoGrandeError,
    abortar_carga_multiparte,
    completar_carga_multiparte,
    iniciar_carga_multiparte,
    listar_partes_subidas,
    obtener_cliente_s3,
    subir_parte,
    validar_tamano,
)

BUCKET = "documentos"


def test_obtener_cliente_s3_usa_el_endpoint_configurado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINIO_ENDPOINT", "minio:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "test")
    monkeypatch.setenv("MINIO_SECRET_KEY", "test-secreto")

    cliente = obtener_cliente_s3()

    assert cliente.meta.endpoint_url == "http://minio:9000"


@pytest.fixture()
def cliente_s3():
    # moto solo intercepta el endpoint estándar de S3; para probar la LÓGICA de
    # multipart/reanudación (independiente de a qué endpoint apunte el cliente)
    # se usa un cliente boto3 plano en vez de obtener_cliente_s3().
    with mock_aws():
        cliente = boto3.client("s3", region_name="us-east-1")
        cliente.create_bucket(Bucket=BUCKET)
        yield cliente


def test_validar_tamano_acepta_hasta_1_gb() -> None:
    validar_tamano(TAMANO_MAXIMO_BYTES)  # no lanza


def test_validar_tamano_rechaza_mas_de_1_gb() -> None:
    with pytest.raises(ArchivoDemasiadoGrandeError):
        validar_tamano(TAMANO_MAXIMO_BYTES + 1)


def test_carga_multiparte_completa_reconstruye_el_archivo(cliente_s3) -> None:
    llave = "area-contabilidad/cierre-enero.xlsx"
    upload_id = iniciar_carga_multiparte(cliente_s3, BUCKET, llave)

    parte1 = subir_parte(cliente_s3, BUCKET, llave, upload_id, 1, b"a" * (5 * 1024 * 1024))
    parte2 = subir_parte(cliente_s3, BUCKET, llave, upload_id, 2, b"b" * 1024)

    completar_carga_multiparte(
        cliente_s3,
        BUCKET,
        llave,
        upload_id,
        partes=[parte1, parte2],
    )

    objeto = cliente_s3.get_object(Bucket=BUCKET, Key=llave)
    contenido = objeto["Body"].read()
    assert len(contenido) == 5 * 1024 * 1024 + 1024


def test_carga_multiparte_es_reanudable_con_partes_ya_subidas(cliente_s3) -> None:
    """Simula un cliente que sube la parte 1, se cae, y reanuda subiendo la parte 2
    con el mismo upload_id (RF-03: carga por partes y reanudable)."""
    llave = "area-contabilidad/reanudable.xlsx"
    upload_id = iniciar_carga_multiparte(cliente_s3, BUCKET, llave)

    # Toda parte que no sea la última debe pesar >= 5 MB (regla real de S3/MinIO).
    parte1 = subir_parte(cliente_s3, BUCKET, llave, upload_id, 1, b"x" * (5 * 1024 * 1024))

    # "reanudación": nueva llamada, mismo upload_id, sin repetir la parte 1
    parte2 = subir_parte(cliente_s3, BUCKET, llave, upload_id, 2, b"y" * 1024)

    completar_carga_multiparte(cliente_s3, BUCKET, llave, upload_id, partes=[parte1, parte2])

    objeto = cliente_s3.get_object(Bucket=BUCKET, Key=llave)
    assert objeto["Body"].read() == b"x" * (5 * 1024 * 1024) + b"y" * 1024


def test_listar_partes_subidas_permite_a_un_cliente_saber_donde_reanudar(cliente_s3) -> None:
    llave = "area-contabilidad/consulta-reanudacion.xlsx"
    upload_id = iniciar_carga_multiparte(cliente_s3, BUCKET, llave)
    subir_parte(cliente_s3, BUCKET, llave, upload_id, 1, b"x" * (5 * 1024 * 1024))

    partes = listar_partes_subidas(cliente_s3, BUCKET, llave, upload_id)

    assert [p["PartNumber"] for p in partes] == [1]
    abortar_carga_multiparte(cliente_s3, BUCKET, llave, upload_id)


def test_abortar_carga_multiparte_cancela_la_carga_pendiente(cliente_s3) -> None:
    from botocore.exceptions import ClientError

    llave = "area-contabilidad/a-cancelar.xlsx"
    upload_id = iniciar_carga_multiparte(cliente_s3, BUCKET, llave)
    subir_parte(cliente_s3, BUCKET, llave, upload_id, 1, b"x" * (5 * 1024 * 1024))

    abortar_carga_multiparte(cliente_s3, BUCKET, llave, upload_id)

    with pytest.raises(ClientError):
        listar_partes_subidas(cliente_s3, BUCKET, llave, upload_id)
