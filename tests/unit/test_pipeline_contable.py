"""Pruebas de integración del pipeline CU-01 dentro del orquestador
(Sprint 1, item 6): parser → reglas → RAG → explicación → salida, disparado
por `ejecutar_analisis` cuando `tipo_revision == "contable"`.
"""

import io
import uuid
from datetime import UTC, date, datetime, timedelta

import boto3
from moto import mock_aws
from openpyxl import Workbook, load_workbook
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from comun.estados import EstadoAnalisis, EstadoDocumento
from comun.modelos import (
    Analisis,
    Area,
    Base,
    Documento,
    Hallazgo,
    Rol,
    TipoRevision,
    Usuario,
    VersionDocumento,
)
from orquestador.tareas import ejecutar_analisis

BUCKET = "documentos"


def _libro_con_cuenta_inexistente() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Partidas"
    ws.append(["Cuenta", "Descripcion", "Fecha", "Debe", "Haber", "Moneda"])
    ws.append(["1010", "Cobro a cliente", date(2026, 1, 5), 100.0, 0.0, "Q"])
    ws.append(["9999", "Cuenta que no existe", date(2026, 1, 5), 0.0, 100.0, "Q"])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _libro_sin_errores() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Partidas"
    ws.append(["Cuenta", "Descripcion", "Fecha", "Debe", "Haber", "Moneda"])
    ws.append(["1010", "Cobro a cliente", date(2026, 1, 5), 100.0, 0.0, "Q"])
    ws.append(["4010", "Ingreso por servicio", date(2026, 1, 5), 0.0, 100.0, "Q"])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _sesion_con_documento_analisis_y_version(
    contenido: bytes,
) -> tuple[Session, uuid.UUID, uuid.UUID, str]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sesion = Session(engine)

    area = Area(nombre="Contabilidad")
    rol = Rol(nombre="analista")
    sesion.add_all([area, rol])
    sesion.flush()

    usuario = Usuario(nombre="Ana Lista", email="ana@ejemplo.gt", area_id=area.id, rol_id=rol.id)
    sesion.add(usuario)
    sesion.flush()

    documento = Documento(
        nombre_original="cierre.xlsx",
        tipo_archivo="xlsx",
        tamano_bytes=len(contenido),
        area_id=area.id,
        usuario_carga_id=usuario.id,
        fecha_carga=datetime.now(UTC),
        fecha_expiracion=date.today() + timedelta(days=90),
        estado=EstadoDocumento.CARGADO.value,
    )
    tipo_revision = TipoRevision(nombre="contable")
    sesion.add_all([documento, tipo_revision])
    sesion.flush()

    analisis = Analisis(
        documento_id=documento.id,
        tipo_revision_id=tipo_revision.id,
        usuario_id=usuario.id,
        fecha_inicio=datetime(2026, 1, 31, tzinfo=UTC),
        estado=EstadoAnalisis.PROCESANDO.value,
    )
    sesion.add(analisis)
    sesion.flush()

    llave = f"{area.id}/{documento.id}/cierre.xlsx"
    version = VersionDocumento(
        documento_id=documento.id,
        numero_version=1,
        ruta_almacenamiento=llave,
        es_corregida=False,
        fecha_creacion=datetime.now(UTC),
    )
    sesion.add(version)
    sesion.commit()

    return sesion, documento.id, analisis.id, llave


def _embedding_falso(_texto: str) -> list[float]:
    return [0.0] * 4


def _llm_falso(_prompt: str) -> str:
    return "Causa probable: prueba. Corrección sugerida: prueba."


def test_ejecutar_analisis_contable_persiste_hallazgos_y_marca_con_hallazgos() -> None:
    contenido = _libro_con_cuenta_inexistente()
    sesion, documento_id, analisis_id, llave = _sesion_con_documento_analisis_y_version(contenido)

    with mock_aws():
        cliente_s3 = boto3.client("s3", region_name="us-east-1")
        cliente_s3.create_bucket(Bucket=BUCKET)
        cliente_s3.put_object(Bucket=BUCKET, Key=llave, Body=contenido)

        resultado = ejecutar_analisis(
            sesion,
            documento_id,
            analisis_id,
            cliente_s3=cliente_s3,
            bucket=BUCKET,
            cliente_qdrant=QdrantClient(":memory:"),
            funcion_embedding=_embedding_falso,
            funcion_llm=_llm_falso,
            modelo_llm="modelo-de-prueba",
        )

        assert resultado == EstadoDocumento.CON_HALLAZGOS.value

        documento = sesion.get(Documento, documento_id)
        analisis = sesion.get(Analisis, analisis_id)
        assert documento.estado == EstadoDocumento.CON_HALLAZGOS.value
        assert analisis.estado == EstadoAnalisis.COMPLETADO.value
        assert analisis.modelo_llm == "modelo-de-prueba"
        assert analisis.version_prompt == "redaccion-contable.v1"

        hallazgos = sesion.query(Hallazgo).filter_by(analisis_id=analisis_id).all()
        assert len(hallazgos) == 1
        assert hallazgos[0].ubicacion == "Partidas!A3"
        assert hallazgos[0].severidad == "alta"
        assert "prueba" in hallazgos[0].correccion_sugerida

        versiones = (
            sesion.query(VersionDocumento)
            .filter_by(documento_id=documento_id)
            .order_by(VersionDocumento.numero_version)
            .all()
        )
        assert len(versiones) == 2
        assert versiones[1].es_corregida is True

        llave_marcada = versiones[1].ruta_almacenamiento
        libro_marcado_bytes = cliente_s3.get_object(Bucket=BUCKET, Key=llave_marcada)["Body"].read()
        wb_marcado = load_workbook(io.BytesIO(libro_marcado_bytes))
        assert wb_marcado["Partidas"]["A3"].comment is not None


def test_ejecutar_analisis_contable_sin_hallazgos_marca_en_revision() -> None:
    contenido = _libro_sin_errores()
    sesion, documento_id, analisis_id, llave = _sesion_con_documento_analisis_y_version(contenido)

    with mock_aws():
        cliente_s3 = boto3.client("s3", region_name="us-east-1")
        cliente_s3.create_bucket(Bucket=BUCKET)
        cliente_s3.put_object(Bucket=BUCKET, Key=llave, Body=contenido)

        resultado = ejecutar_analisis(
            sesion,
            documento_id,
            analisis_id,
            cliente_s3=cliente_s3,
            bucket=BUCKET,
            cliente_qdrant=QdrantClient(":memory:"),
            funcion_embedding=_embedding_falso,
            funcion_llm=_llm_falso,
            modelo_llm="modelo-de-prueba",
        )

        assert resultado == EstadoDocumento.EN_REVISION.value
        assert sesion.query(Hallazgo).filter_by(analisis_id=analisis_id).count() == 0

        versiones = sesion.query(VersionDocumento).filter_by(documento_id=documento_id).all()
        assert len(versiones) == 1  # no se sube versión corregida si no hay hallazgos


def test_ejecutar_analisis_sin_dependencias_de_infraestructura_usa_flujo_generico() -> None:
    """Si no se inyectan las dependencias de RAG/S3 (p. ej. un tipo de revisión
    sin adaptador todavía), se preserva el comportamiento genérico de L2."""
    contenido = _libro_con_cuenta_inexistente()
    sesion, documento_id, analisis_id, _llave = _sesion_con_documento_analisis_y_version(contenido)

    resultado = ejecutar_analisis(sesion, documento_id, analisis_id)

    assert resultado == EstadoDocumento.EN_REVISION.value
    assert sesion.query(Hallazgo).filter_by(analisis_id=analisis_id).count() == 0
