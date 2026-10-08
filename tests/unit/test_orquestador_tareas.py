import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import boto3
import cv2
import numpy as np
from moto import mock_aws
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from comun.estados import EstadoAnalisis, EstadoDocumento
from comun.modelos import (
    Analisis,
    Area,
    Base,
    Bitacora,
    Documento,
    Hallazgo,
    Rol,
    TipoRevision,
    Usuario,
    VersionDocumento,
)
from orquestador.tareas import ejecutar_analisis

BUCKET = "documentos"


def _sesion_con_documento_y_analisis() -> tuple[Session, uuid.UUID, uuid.UUID]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sesion = Session(engine)

    area = Area(nombre="Contabilidad")
    rol = Rol(nombre="analista")
    sesion.add_all([area, rol])
    sesion.flush()

    usuario = Usuario(
        nombre="Ana Lista",
        email="ana@ejemplo.gt",
        area_id=area.id,
        rol_id=rol.id,
    )
    sesion.add(usuario)
    sesion.flush()

    documento = Documento(
        nombre_original="cierre.xlsx",
        tipo_archivo="xlsx",
        tamano_bytes=100,
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
        fecha_inicio=datetime.now(UTC),
        estado=EstadoAnalisis.PROCESANDO.value,
    )
    sesion.add(analisis)
    sesion.commit()

    return sesion, documento.id, analisis.id


def test_ejecutar_analisis_transiciona_a_en_revision_y_registra_bitacora() -> None:
    sesion, documento_id, analisis_id = _sesion_con_documento_y_analisis()

    ejecutar_analisis(sesion, documento_id, analisis_id)

    documento = sesion.get(Documento, documento_id)
    analisis = sesion.get(Analisis, analisis_id)
    assert documento.estado == EstadoDocumento.EN_REVISION.value
    assert analisis.estado == EstadoAnalisis.COMPLETADO.value
    assert analisis.fecha_fin is not None

    acciones = [b.accion for b in sesion.query(Bitacora).order_by(Bitacora.fecha_hora).all()]
    assert "analisis_iniciado" in acciones
    assert "analisis_completado" in acciones


def test_ejecutar_analisis_marca_fallido_si_el_documento_no_existe() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sesion = Session(engine)

    resultado = ejecutar_analisis(sesion, uuid.uuid4(), uuid.uuid4())

    assert resultado == EstadoDocumento.FALLIDO.value


def _png_bytes() -> bytes:
    imagen = np.full((30, 40, 3), 255, dtype=np.uint8)
    ok, buffer = cv2.imencode(".png", imagen)
    assert ok
    return buffer.tobytes()


def _datos_ocr_falsos(texto: str) -> dict[str, list[Any]]:
    return {
        "block_num": [1],
        "par_num": [1],
        "line_num": [1],
        "left": [5],
        "top": [5],
        "width": [30],
        "height": [10],
        "conf": [90.0],
        "text": [texto],
    }


def test_ejecutar_analisis_ocr_publica_version_con_el_texto_reconocido() -> None:
    contenido = _png_bytes()

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
        nombre_original="escaneo.png",
        tipo_archivo="png",
        tamano_bytes=len(contenido),
        area_id=area.id,
        usuario_carga_id=usuario.id,
        fecha_carga=datetime.now(UTC),
        fecha_expiracion=date.today() + timedelta(days=90),
        estado=EstadoDocumento.CARGADO.value,
    )
    tipo_revision = TipoRevision(nombre="ocr")
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

    llave = f"{area.id}/{documento.id}/escaneo.png"
    version = VersionDocumento(
        documento_id=documento.id,
        numero_version=1,
        ruta_almacenamiento=llave,
        es_corregida=False,
        fecha_creacion=datetime.now(UTC),
    )
    sesion.add(version)
    sesion.commit()

    with mock_aws():
        cliente_s3 = boto3.client("s3", region_name="us-east-1")
        cliente_s3.create_bucket(Bucket=BUCKET)
        cliente_s3.put_object(Bucket=BUCKET, Key=llave, Body=contenido)

        resultado = ejecutar_analisis(
            sesion,
            documento.id,
            analisis.id,
            cliente_s3=cliente_s3,
            bucket=BUCKET,
            funcion_ocr=lambda _img: _datos_ocr_falsos("Texto reconocido"),
            funcion_osd=lambda _img: 0,
        )

        assert resultado == EstadoDocumento.EN_REVISION.value

        versiones = (
            sesion.query(VersionDocumento)
            .filter_by(documento_id=documento.id)
            .order_by(VersionDocumento.numero_version)
            .all()
        )
        assert len(versiones) == 2
        assert versiones[1].es_corregida is True

        objeto = cliente_s3.get_object(Bucket=BUCKET, Key=versiones[1].ruta_almacenamiento)
        assert objeto["Body"].read() == b"Texto reconocido"

        # Bloque 3 (bitácora: "...páginas, confianza media, páginas ilegibles").
        acciones = [b.accion for b in sesion.query(Bitacora).order_by(Bitacora.fecha_hora).all()]
        assert "ocr_completado" in acciones
        entrada = next(b for b in sesion.query(Bitacora).all() if b.accion == "ocr_completado")
        assert "página(s)" in entrada.detalle
        assert "confianza media" in entrada.detalle


def test_ejecutar_analisis_ocr_pagina_ilegible_marca_con_hallazgos() -> None:
    """Bloque 2 (RN-06): una página ilegible no falla el análisis -- lo
    completa con un aviso (Hallazgo), nunca texto inventado."""
    contenido = _png_bytes()

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
        nombre_original="escaneo.png",
        tipo_archivo="png",
        tamano_bytes=len(contenido),
        area_id=area.id,
        usuario_carga_id=usuario.id,
        fecha_carga=datetime.now(UTC),
        fecha_expiracion=date.today() + timedelta(days=90),
        estado=EstadoDocumento.CARGADO.value,
    )
    tipo_revision = TipoRevision(nombre="ocr")
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

    llave = f"{area.id}/{documento.id}/escaneo.png"
    version = VersionDocumento(
        documento_id=documento.id,
        numero_version=1,
        ruta_almacenamiento=llave,
        es_corregida=False,
        fecha_creacion=datetime.now(UTC),
    )
    sesion.add(version)
    sesion.commit()

    with mock_aws():
        cliente_s3 = boto3.client("s3", region_name="us-east-1")
        cliente_s3.create_bucket(Bucket=BUCKET)
        cliente_s3.put_object(Bucket=BUCKET, Key=llave, Body=contenido)

        def _datos_pagina_ilegible(_img: Any) -> dict[str, list[Any]]:
            return {
                "block_num": [1],
                "par_num": [1],
                "line_num": [1],
                "left": [5],
                "top": [5],
                "width": [30],
                "height": [10],
                "conf": [20.0],  # < OCR_PAGINA_ILEGIBLE (50 por defecto)
                "text": ["##!!garabato"],
            }

        resultado = ejecutar_analisis(
            sesion,
            documento.id,
            analisis.id,
            cliente_s3=cliente_s3,
            bucket=BUCKET,
            funcion_ocr=_datos_pagina_ilegible,
            funcion_osd=lambda _img: 0,
        )

        assert resultado == EstadoDocumento.CON_HALLAZGOS.value

        hallazgos = sesion.query(Hallazgo).filter_by(analisis_id=analisis.id).all()
        assert len(hallazgos) == 1
        assert hallazgos[0].ubicacion == "Documento completo"
        assert "ilegible" in hallazgos[0].descripcion

        versiones = (
            sesion.query(VersionDocumento)
            .filter_by(documento_id=documento.id)
            .order_by(VersionDocumento.numero_version)
            .all()
        )
        texto_publicado = cliente_s3.get_object(
            Bucket=BUCKET, Key=versiones[1].ruta_almacenamiento
        )["Body"].read()
        assert b"ilegible" in texto_publicado
        assert b"garabato" not in texto_publicado
