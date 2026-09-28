"""Pruebas de integración del pipeline CU-05 (Bloque O4): extracción →
revisión ortográfica (RN-06) → persistencia, disparado por `ejecutar_analisis`
cuando `tipo_revision == "ortografia"`.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import boto3
from moto import mock_aws
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
from ortografia.cliente_languagetool import CoincidenciaLT

BUCKET = "documentos"
GLOSARIO = {"SFC", "SAT"}


def _sesion_con_documento_analisis_y_version(
    contenido: bytes, *, tipo_archivo: str = "txt", nombre: str = "texto.txt"
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
        nombre_original=nombre,
        tipo_archivo=tipo_archivo,
        tamano_bytes=len(contenido),
        area_id=area.id,
        usuario_carga_id=usuario.id,
        fecha_carga=datetime.now(UTC),
        fecha_expiracion=date.today() + timedelta(days=90),
        estado=EstadoDocumento.CARGADO.value,
    )
    tipo_revision = TipoRevision(nombre="ortografia")
    sesion.add_all([documento, tipo_revision])
    sesion.flush()

    analisis = Analisis(
        documento_id=documento.id,
        tipo_revision_id=tipo_revision.id,
        usuario_id=usuario.id,
        fecha_inicio=datetime.now(UTC),
        estado=EstadoAnalisis.PROCESANDO.value,
    )
    sesion.add(analisis)
    sesion.flush()

    llave = f"{area.id}/{documento.id}/{nombre}"
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


def _lt_falso_una_coincidencia_typos(texto: str) -> list[CoincidenciaLT]:
    if "aprovado" not in texto:
        return []
    inicio = texto.index("aprovado")
    return [
        CoincidenciaLT(
            texto="aprovado",
            offset=inicio,
            longitud=len("aprovado"),
            mensaje="Posible error ortográfico",
            sugerencias=["aprobado"],
            regla_id="MORFOLOGIK_RULE_ES",
            categoria="TYPOS",
        )
    ]


def _llm_no_deberia_llamarse(_prompt: str) -> str:
    raise AssertionError("no debía llamarse al LLM: no hay casos dudosos en este documento")


def test_ejecutar_analisis_ortografia_persiste_hallazgo_determinista() -> None:
    contenido = b"Este procedimiento fue aprovado por la gerencia del SFC."
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
            funcion_revisar_lt=_lt_falso_una_coincidencia_typos,
            funcion_llm=_llm_no_deberia_llamarse,
        )

        assert resultado == EstadoDocumento.CON_HALLAZGOS.value

        hallazgos = sesion.query(Hallazgo).filter_by(analisis_id=analisis_id).all()
        assert len(hallazgos) == 1
        assert hallazgos[0].ubicacion == "Texto"
        assert hallazgos[0].texto_original == "aprovado"
        assert hallazgos[0].correccion_sugerida == "aprobado"
        assert hallazgos[0].estado == "pendiente"


def test_termino_de_glosario_no_genera_hallazgo_en_el_pipeline() -> None:
    contenido = "La SFC revisó el procedimiento.".encode()
    sesion, documento_id, analisis_id, llave = _sesion_con_documento_analisis_y_version(contenido)

    def lt_falso(_texto: str) -> list[CoincidenciaLT]:
        return [
            CoincidenciaLT(
                texto="SFC",
                offset=3,
                longitud=3,
                mensaje="no reconocida",
                sugerencias=[],
                regla_id="MORFOLOGIK_RULE_ES",
                categoria="TYPOS",
            )
        ]

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
            funcion_revisar_lt=lt_falso,
            funcion_llm=_llm_no_deberia_llamarse,
        )

        assert resultado == EstadoDocumento.EN_REVISION.value
        assert sesion.query(Hallazgo).filter_by(analisis_id=analisis_id).count() == 0


def test_pdf_sin_texto_marca_el_analisis_fallido_con_detalle_en_bitacora() -> None:
    import pymupdf

    from comun.modelos import Bitacora

    documento_pdf = pymupdf.open()
    documento_pdf.new_page()
    contenido = documento_pdf.tobytes()
    documento_pdf.close()

    sesion, documento_id, analisis_id, llave = _sesion_con_documento_analisis_y_version(
        contenido, tipo_archivo="pdf", nombre="escaneado.pdf"
    )

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
            funcion_revisar_lt=_lt_falso_una_coincidencia_typos,
            funcion_llm=_llm_no_deberia_llamarse,
        )

        assert resultado == EstadoDocumento.FALLIDO.value
        analisis = sesion.get(Analisis, analisis_id)
        assert analisis.estado == EstadoAnalisis.FALLIDO.value

        bitacora = (
            sesion.query(Bitacora)
            .filter_by(entidad_id=analisis_id, accion="analisis_fallido")
            .one()
        )
        assert "OCR" in bitacora.detalle
