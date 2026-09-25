import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from comun.modelos import (
    Analisis,
    Area,
    Bitacora,
    Decision,
    Documento,
    Fragmento,
    FuenteConocimiento,
    Glosario,
    Hallazgo,
    Permiso,
    Regla,
    Rol,
    TipoRevision,
    Usuario,
    VersionDocumento,
)
from comun.modelos import Base as ModelosBase


def _sesion_en_memoria() -> Session:
    engine = create_engine("sqlite:///:memory:")
    ModelosBase.metadata.create_all(engine)
    return Session(engine)


def test_crea_las_15_entidades_del_modelo_er() -> None:
    tablas = set(ModelosBase.metadata.tables.keys())
    esperadas = {
        "area",
        "rol",
        "permiso",
        "usuario",
        "documento",
        "version_documento",
        "tipo_revision",
        "analisis",
        "hallazgo",
        "decision",
        "fuente_conocimiento",
        "fragmento",
        "regla",
        "glosario",
        "bitacora",
    }
    assert esperadas <= tablas


def test_flujo_completo_cu01_persiste_y_relaciona_correctamente() -> None:
    sesion = _sesion_en_memoria()

    area = Area(nombre="Contabilidad")
    rol_analista = Rol(nombre="analista", descripcion="Carga y ejecuta análisis")
    sesion.add_all([area, rol_analista])
    sesion.flush()

    Permiso(rol_id=rol_analista.id, recurso="documento", accion="crear")

    analista = Usuario(
        nombre="Ana Lista",
        email="ana@ejemplo.gt",
        area_id=area.id,
        rol_id=rol_analista.id,
        origen_autenticacion="local",
        activo=True,
    )
    sesion.add(analista)
    sesion.flush()

    documento = Documento(
        nombre_original="cierre-enero.xlsx",
        tipo_archivo="xlsx",
        tamano_bytes=1024,
        area_id=area.id,
        usuario_carga_id=analista.id,
        fecha_carga=datetime.now(UTC),
        fecha_expiracion=date.today() + timedelta(days=90),
        estado="cargado",
    )
    sesion.add(documento)
    sesion.flush()

    version = VersionDocumento(
        documento_id=documento.id,
        numero_version=1,
        ruta_almacenamiento="documentos/cierre-enero.xlsx",
        es_corregida=False,
        fecha_creacion=datetime.now(UTC),
    )
    tipo_revision = TipoRevision(nombre="contable")
    sesion.add_all([version, tipo_revision])
    sesion.flush()

    analisis = Analisis(
        documento_id=documento.id,
        tipo_revision_id=tipo_revision.id,
        usuario_id=analista.id,
        fecha_inicio=datetime.now(UTC),
        estado="procesando",
    )
    sesion.add(analisis)
    sesion.flush()

    fuente = FuenteConocimiento(
        nombre="Catálogo de cuentas",
        area_id=area.id,
        curador_id=analista.id,
        version="1.0",
        vigente_desde=date.today(),
        estado="vigente",
        ruta_archivo="fuentes/catalogo.pdf",
    )
    sesion.add(fuente)
    sesion.flush()

    fragmento = Fragmento(fuente_id=fuente.id, contenido="Cuenta 1010 - Caja")
    regla = Regla(
        codigo="RN-01",
        descripcion="Cuadre debe/haber",
        area_id=area.id,
        tipo_documento="xlsx",
        severidad="alta",
        fuente_id=fuente.id,
        vigente_desde=date.today(),
        version="1.0",
        estado="vigente",
    )
    glosario = Glosario(area_id=area.id, termino="NIIF", definicion="Normas...")
    sesion.add_all([fragmento, regla, glosario])
    sesion.flush()

    hallazgo = Hallazgo(
        analisis_id=analisis.id,
        version_documento_id=version.id,
        regla_id=regla.id,
        fragmento_id=fragmento.id,
        severidad="alta",
        ubicacion="Hoja1!C15",
        descripcion="Descuadre de Q100.00",
        correccion_sugerida="Revisar partida",
        monto=100.00,
        moneda="Q",
        estado="pendiente",
    )
    sesion.add(hallazgo)
    sesion.flush()

    decision = Decision(
        hallazgo_id=hallazgo.id,
        usuario_id=analista.id,
        resultado="aceptado",
        fecha=datetime.now(UTC),
    )
    bitacora = Bitacora(
        usuario_id=analista.id,
        accion="crear_documento",
        entidad_tipo="documento",
        entidad_id=documento.id,
        fecha_hora=datetime.now(UTC),
    )
    sesion.add_all([decision, bitacora])
    sesion.commit()

    recuperado = sesion.get(Hallazgo, hallazgo.id)
    assert recuperado is not None
    assert recuperado.moneda == "Q"
    assert recuperado.regla_id == regla.id

    assert sesion.get(Documento, documento.id).estado == "cargado"
    assert isinstance(documento.id, uuid.UUID)
