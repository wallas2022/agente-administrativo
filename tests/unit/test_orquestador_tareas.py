import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from comun.estados import EstadoAnalisis, EstadoDocumento
from comun.modelos import Analisis, Area, Base, Bitacora, Documento, Rol, TipoRevision, Usuario
from orquestador.tareas import ejecutar_analisis


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
