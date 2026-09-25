"""Almacenamiento de documentos (API S3) — carga por partes y reanudable.

Relacionado con: RF-03 (tamaño máx. 1 GB, carga por partes y reanudable), RN-09.
Cliente boto3 genérico contra cualquier backend compatible con la API S3 (en
local, LocalStack — ver docs/04-pruebas/resultados/local-localstack.md; MinIO
descontinuó su distribución gratuita). Expone las primitivas de multipart
upload (incluida la reanudación mediante `upload_id`) de forma directa.
"""

import os
from typing import TypedDict

import boto3
from botocore.client import BaseClient
from botocore.config import Config

TAMANO_MAXIMO_BYTES = 1024 * 1024 * 1024  # 1 GB — RF-03, RN-09


class ArchivoDemasiadoGrandeError(ValueError):
    pass


def validar_tamano(tamano_bytes: int) -> None:
    if tamano_bytes > TAMANO_MAXIMO_BYTES:
        raise ArchivoDemasiadoGrandeError(
            f"{tamano_bytes} bytes supera el máximo permitido de {TAMANO_MAXIMO_BYTES} bytes (1 GB)"
        )


def obtener_cliente_s3() -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("MINIO_ENDPOINT_URL")
        or f"http://{os.environ.get('MINIO_ENDPOINT', 'localstack:4566')}",
        aws_access_key_id=os.environ.get("MINIO_ACCESS_KEY", ""),
        aws_secret_access_key=os.environ.get("MINIO_SECRET_KEY", ""),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        region_name="us-east-1",
    )


def iniciar_carga_multiparte(cliente: BaseClient, bucket: str, llave: str) -> str:
    respuesta = cliente.create_multipart_upload(Bucket=bucket, Key=llave)
    return respuesta["UploadId"]


class ParteSubida(TypedDict):
    PartNumber: int
    ETag: str


def subir_parte(
    cliente: BaseClient,
    bucket: str,
    llave: str,
    upload_id: str,
    numero_parte: int,
    datos: bytes,
) -> ParteSubida:
    respuesta = cliente.upload_part(
        Bucket=bucket,
        Key=llave,
        UploadId=upload_id,
        PartNumber=numero_parte,
        Body=datos,
    )
    return {"PartNumber": numero_parte, "ETag": respuesta["ETag"]}


def listar_partes_subidas(
    cliente: BaseClient, bucket: str, llave: str, upload_id: str
) -> list[ParteSubida]:
    """Permite a un cliente que reanuda una carga saber qué partes ya llegaron."""
    respuesta = cliente.list_parts(Bucket=bucket, Key=llave, UploadId=upload_id)
    return [
        {"PartNumber": p["PartNumber"], "ETag": p["ETag"]} for p in respuesta.get("Parts", [])
    ]


def completar_carga_multiparte(
    cliente: BaseClient,
    bucket: str,
    llave: str,
    upload_id: str,
    partes: list[ParteSubida],
) -> None:
    partes_ordenadas = sorted(partes, key=lambda p: p["PartNumber"])
    cliente.complete_multipart_upload(
        Bucket=bucket,
        Key=llave,
        UploadId=upload_id,
        MultipartUpload={"Parts": partes_ordenadas},
    )


def abortar_carga_multiparte(cliente: BaseClient, bucket: str, llave: str, upload_id: str) -> None:
    cliente.abort_multipart_upload(Bucket=bucket, Key=llave, UploadId=upload_id)


def asegurar_bucket(cliente: BaseClient, bucket: str) -> None:
    buckets_existentes = {b["Name"] for b in cliente.list_buckets().get("Buckets", [])}
    if bucket not in buckets_existentes:
        cliente.create_bucket(Bucket=bucket)


def descargar_objeto(cliente: BaseClient, bucket: str, llave: str) -> bytes:
    respuesta = cliente.get_object(Bucket=bucket, Key=llave)
    return respuesta["Body"].read()


def subir_objeto(cliente: BaseClient, bucket: str, llave: str, contenido: bytes) -> None:
    cliente.put_object(Bucket=bucket, Key=llave, Body=contenido)
