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
from orquestador import tareas
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


def test_analizar_documento_envuelve_llm_y_embedding_con_contexto_del_analisis(
    monkeypatch,
) -> None:
    """P-13 (Bloque 1, RF-21): analizar_documento (la tarea Celery, no
    ejecutar_analisis) resuelve analisis/documento/tipo_revision una vez
    para poder envolver funcion_llm/funcion_embedding con usuario, área,
    análisis y caso de uso -- sin tocar la firma de ejecutar_analisis (sigue
    siendo lógica pura, probada arriba con funciones falsas)."""
    import httpx

    sesion, documento_id, analisis_id = _sesion_con_documento_y_analisis()

    monkeypatch.setattr(tareas, "obtener_fabrica_sesion", lambda: (lambda: sesion))

    capturado: dict[str, Any] = {}

    def _ejecutar_analisis_falso(_sesion, _documento_id, _analisis_id, **kwargs):
        capturado.update(kwargs)
        return EstadoDocumento.EN_REVISION.value

    monkeypatch.setattr(tareas, "ejecutar_analisis", _ejecutar_analisis_falso)
    monkeypatch.setattr(
        "comun.glosario.cargar_glosario", lambda: set(), raising=False
    )

    resultado = tareas.analizar_documento(str(documento_id), str(analisis_id))

    assert resultado == EstadoDocumento.EN_REVISION.value
    funcion_llm_envuelta = capturado["funcion_llm"]
    funcion_embedding_envuelta = capturado["funcion_embedding"]

    class _RespuestaChatFalsa:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"message": {"content": "explicación generada"}, "eval_count": 30}

    monkeypatch.setattr(
        httpx, "post", lambda url, *, json, timeout: _RespuestaChatFalsa()
    )
    texto = funcion_llm_envuelta("prompt de prueba")
    assert texto == "explicación generada"

    class _RespuestaEmbedFalsa:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"embeddings": [[0.1, 0.2]]}

    monkeypatch.setattr(
        httpx, "post", lambda url, *, json, timeout: _RespuestaEmbedFalsa()
    )
    vector = funcion_embedding_envuelta("texto de búsqueda")
    assert vector == [0.1, 0.2]

    from comun.modelos import UsoLlm

    usos = {u.caso_uso: u for u in sesion.query(UsoLlm).all()}
    assert usos["contable"].resultado == "ok"
    assert usos["contable"].tokens_salida == 30
    assert usos["embeddings_busqueda"].resultado == "ok"
    assert usos["contable"].usuario_id == sesion.get(Analisis, analisis_id).usuario_id


def test_validar_dudosos_ortografia_envuelve_funcion_llm_con_contexto_del_analisis(
    monkeypatch,
) -> None:
    """P-13 (Bloque 1, RF-21): mismo patrón que analizar_documento, para la
    tarea async de CU-05 (confirma/descarta dudosos de ortografía)."""
    import httpx

    sesion, documento_id, analisis_id = _sesion_con_documento_y_analisis()
    tipo_revision = sesion.get(Analisis, analisis_id).tipo_revision_id
    sesion.get(TipoRevision, tipo_revision).nombre = "ortografia"
    sesion.commit()

    monkeypatch.setattr(tareas, "obtener_fabrica_sesion", lambda: (lambda: sesion))

    capturado: dict[str, Any] = {}

    def _ejecutar_validacion_falsa(_sesion, _analisis_id, **kwargs):
        capturado.update(kwargs)

    monkeypatch.setattr(
        tareas, "ejecutar_validacion_dudosos_ortografia", _ejecutar_validacion_falsa
    )

    tareas.validar_dudosos_ortografia(str(analisis_id))

    funcion_llm_envuelta = capturado["funcion_llm"]

    class _RespuestaChatFalsa:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"message": {"content": "confirmado"}, "eval_count": 12}

    monkeypatch.setattr(
        httpx, "post", lambda url, *, json, timeout: _RespuestaChatFalsa()
    )
    texto = funcion_llm_envuelta("prompt de prueba")
    assert texto == "confirmado"

    from comun.modelos import UsoLlm

    fila = sesion.query(UsoLlm).filter_by(caso_uso="ortografia").one()
    assert fila.resultado == "ok"
    assert fila.tokens_salida == 12
    assert fila.usuario_id == sesion.get(Analisis, analisis_id).usuario_id
