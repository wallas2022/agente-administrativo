"""Pruebas de integración del pipeline CU-05 (Bloque O4): extracción →
revisión ortográfica (RN-06) → persistencia, disparado por `ejecutar_analisis`
cuando `tipo_revision == "ortografia"`.
"""

import json
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
    Bitacora,
    Documento,
    Hallazgo,
    Rol,
    TipoRevision,
    Usuario,
    VersionDocumento,
)
from orquestador.tareas import ejecutar_analisis, ejecutar_validacion_dudosos_ortografia
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


def _lt_falso_un_caso_dudoso(texto: str) -> list[CoincidenciaLT]:
    if "de seguimiento" not in texto:
        return []
    return [
        CoincidenciaLT(
            texto="de",
            offset=texto.index("de seguimiento"),
            longitud=2,
            mensaje="Posible falta de tilde diacrítica",
            sugerencias=["dé"],
            regla_id="DE_TILDE",
            categoria="DIACRITICS",
        )
    ]


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


def test_error_inesperado_marca_fallido_en_vez_de_dejar_procesando_para_siempre() -> None:
    """Encontrado en vivo (Bloque O4): una caída transitoria de la conexión
    a Postgres a mitad del pipeline (no un PdfSinTextoError) dejaba el
    análisis atascado en "procesando" para siempre -- ejecutar_analisis debe
    capturar cualquier excepción del pipeline, no solo la de PDF sin texto."""
    from comun.modelos import Bitacora

    contenido = b"Texto de prueba"
    sesion, documento_id, analisis_id, llave = _sesion_con_documento_analisis_y_version(contenido)

    def lt_que_falla(_texto: str) -> list[CoincidenciaLT]:
        raise ConnectionError("se cortó la conexión a mitad de la revisión")

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
            funcion_revisar_lt=lt_que_falla,
            funcion_llm=_llm_no_deberia_llamarse,
        )

        assert resultado == EstadoDocumento.FALLIDO.value
        analisis = sesion.get(Analisis, analisis_id)
        assert analisis.estado == EstadoAnalisis.FALLIDO.value
        documento = sesion.get(Documento, documento_id)
        assert documento.estado == EstadoDocumento.FALLIDO.value

        bitacora = (
            sesion.query(Bitacora)
            .filter_by(entidad_id=analisis_id, accion="analisis_fallido")
            .one()
        )
        assert "se cortó la conexión" in bitacora.detalle


def test_ejecutar_analisis_ortografia_con_dudosos_los_deja_en_validacion_y_encola_fase_2() -> None:
    """RNF-04 (Bloque O6): con una forma de encolar la fase 2, el análisis
    llega a un estado terminal sin llamar al LLM -- el caso dudoso queda
    "en_validacion" y se encola para resolverse en segundo plano."""
    contenido = b"Es necesario que se de seguimiento al hallazgo."
    sesion, documento_id, analisis_id, llave = _sesion_con_documento_analisis_y_version(contenido)

    llamadas_encolar: list[str] = []

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
            funcion_revisar_lt=_lt_falso_un_caso_dudoso,
            funcion_llm=_llm_no_deberia_llamarse,
            funcion_encolar_validacion_dudosos=llamadas_encolar.append,
        )

        assert resultado == EstadoDocumento.CON_HALLAZGOS.value
        assert llamadas_encolar == [str(analisis_id)]

        hallazgo = sesion.query(Hallazgo).filter_by(analisis_id=analisis_id).one()
        assert hallazgo.estado == "en_validacion"
        assert hallazgo.texto_original == "de"
        assert hallazgo.correccion_sugerida == "dé"
        assert hallazgo.fuente_citada == "DE_TILDE"

        analisis = sesion.get(Analisis, analisis_id)
        assert analisis.estado == EstadoAnalisis.COMPLETADO.value


def test_ejecutar_analisis_ortografia_sin_encolar_resuelve_dudosos_de_forma_sincrona() -> None:
    """Sin `funcion_encolar_validacion_dudosos` (p. ej. un entorno sin
    Celery), la fase 2 corre en el mismo `ejecutar_analisis` -- no cambia el
    comportamiento previo a RNF-04/Bloque O6 para quien no pidió la fase
    asíncrona."""
    contenido = b"Es necesario que se de seguimiento al hallazgo."
    sesion, documento_id, analisis_id, llave = _sesion_con_documento_analisis_y_version(contenido)

    def llm_confirma(_prompt: str) -> str:
        return json.dumps(
            [{"indice": 0, "es_error": True, "sugerencia": "dé", "explicacion": "falta la tilde"}]
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
            funcion_revisar_lt=_lt_falso_un_caso_dudoso,
            funcion_llm=llm_confirma,
        )

        assert resultado == EstadoDocumento.CON_HALLAZGOS.value
        hallazgo = sesion.query(Hallazgo).filter_by(analisis_id=analisis_id).one()
        assert hallazgo.estado == "confirmado"
        assert hallazgo.correccion_sugerida == "dé"
        assert hallazgo.fuente_citada is None


def test_ejecutar_validacion_dudosos_ortografia_confirma_y_descarta() -> None:
    contenido = "Es necesario que se de seguimiento; en Agosto se revisó todo.".encode()
    sesion, documento_id, analisis_id, llave = _sesion_con_documento_analisis_y_version(contenido)

    llamadas_encolar: list[str] = []
    with mock_aws():
        cliente_s3 = boto3.client("s3", region_name="us-east-1")
        cliente_s3.create_bucket(Bucket=BUCKET)
        cliente_s3.put_object(Bucket=BUCKET, Key=llave, Body=contenido)

        ejecutar_analisis(
            sesion,
            documento_id,
            analisis_id,
            cliente_s3=cliente_s3,
            bucket=BUCKET,
            funcion_revisar_lt=_lt_falso_un_caso_dudoso,
            funcion_llm=_llm_no_deberia_llamarse,
            funcion_encolar_validacion_dudosos=llamadas_encolar.append,
        )

        def llm_confirma(_prompt: str) -> str:
            return json.dumps(
                [{"indice": 0, "es_error": True, "sugerencia": "dé", "explicacion": "corregido"}]
            )

        ejecutar_validacion_dudosos_ortografia(
            sesion,
            analisis_id,
            cliente_s3=cliente_s3,
            bucket=BUCKET,
            funcion_llm=llm_confirma,
        )

        hallazgo = sesion.query(Hallazgo).filter_by(analisis_id=analisis_id).one()
        assert hallazgo.estado == "confirmado"
        assert hallazgo.correccion_sugerida == "dé"
        assert hallazgo.fuente_citada is None

        bitacora = (
            sesion.query(Bitacora)
            .filter_by(entidad_id=analisis_id, accion="ortografia_dudosos_validados")
            .one()
        )
        assert "1 caso" in bitacora.detalle

        # documento/analisis ya estaban en su estado terminal desde la fase 1
        # y la fase 2 no los toca.
        analisis = sesion.get(Analisis, analisis_id)
        assert analisis.estado == EstadoAnalisis.COMPLETADO.value


def test_ejecutar_validacion_dudosos_ortografia_error_no_marca_fallido_deja_en_validacion() -> None:
    """Un error en la fase 2 (p. ej. el LLM no responde) NO debe revertir el
    estado terminal que el análisis ya alcanzó en la fase 1 -- el hallazgo
    simplemente queda "en_validacion" y el error queda en la bitácora."""
    contenido = b"Es necesario que se de seguimiento al hallazgo."
    sesion, documento_id, analisis_id, llave = _sesion_con_documento_analisis_y_version(contenido)

    llamadas_encolar: list[str] = []
    with mock_aws():
        cliente_s3 = boto3.client("s3", region_name="us-east-1")
        cliente_s3.create_bucket(Bucket=BUCKET)
        cliente_s3.put_object(Bucket=BUCKET, Key=llave, Body=contenido)

        ejecutar_analisis(
            sesion,
            documento_id,
            analisis_id,
            cliente_s3=cliente_s3,
            bucket=BUCKET,
            funcion_revisar_lt=_lt_falso_un_caso_dudoso,
            funcion_llm=_llm_no_deberia_llamarse,
            funcion_encolar_validacion_dudosos=llamadas_encolar.append,
        )

        def llm_que_falla(_prompt: str) -> str:
            raise ConnectionError("el LLM no respondió a tiempo")

        ejecutar_validacion_dudosos_ortografia(
            sesion,
            analisis_id,
            cliente_s3=cliente_s3,
            bucket=BUCKET,
            funcion_llm=llm_que_falla,
        )

        hallazgo = sesion.query(Hallazgo).filter_by(analisis_id=analisis_id).one()
        assert hallazgo.estado == "en_validacion"

        analisis = sesion.get(Analisis, analisis_id)
        assert analisis.estado == EstadoAnalisis.COMPLETADO.value
        documento = sesion.get(Documento, documento_id)
        assert documento.estado == EstadoDocumento.CON_HALLAZGOS.value

        bitacora = (
            sesion.query(Bitacora)
            .filter_by(entidad_id=analisis_id, accion="ortografia_dudosos_fallo")
            .one()
        )
        assert "el LLM no respondió a tiempo" in bitacora.detalle


def test_ejecutar_validacion_dudosos_ortografia_si_hasta_el_rollback_falla_no_revienta() -> None:
    """Encontrado en vivo (Bloque O6): con Postgres ya inestable, el propio
    `sesion.rollback()` del manejo de errores puede fallar también -- eso NO
    debe propagarse sin control y tumbar la tarea de Celery."""
    contenido = b"Es necesario que se de seguimiento al hallazgo."
    sesion, documento_id, analisis_id, llave = _sesion_con_documento_analisis_y_version(contenido)

    llamadas_encolar: list[str] = []
    with mock_aws():
        cliente_s3 = boto3.client("s3", region_name="us-east-1")
        cliente_s3.create_bucket(Bucket=BUCKET)
        cliente_s3.put_object(Bucket=BUCKET, Key=llave, Body=contenido)

        ejecutar_analisis(
            sesion,
            documento_id,
            analisis_id,
            cliente_s3=cliente_s3,
            bucket=BUCKET,
            funcion_revisar_lt=_lt_falso_un_caso_dudoso,
            funcion_llm=_llm_no_deberia_llamarse,
            funcion_encolar_validacion_dudosos=llamadas_encolar.append,
        )

        def llm_que_falla(_prompt: str) -> str:
            raise ConnectionError("el LLM no respondió a tiempo")

        rollback_original = sesion.rollback

        def rollback_que_tambien_falla() -> None:
            rollback_original()
            raise ConnectionError("la conexión a Postgres también se cayó")

        sesion.rollback = rollback_que_tambien_falla  # type: ignore[method-assign]
        try:
            ejecutar_validacion_dudosos_ortografia(
                sesion,
                analisis_id,
                cliente_s3=cliente_s3,
                bucket=BUCKET,
                funcion_llm=llm_que_falla,
            )
        finally:
            sesion.rollback = rollback_original  # type: ignore[method-assign]

        hallazgo = sesion.query(Hallazgo).filter_by(analisis_id=analisis_id).one()
        assert hallazgo.estado == "en_validacion"
