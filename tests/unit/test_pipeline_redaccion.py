"""Pruebas del pipeline CU-02 (fase 1, determinista): extracción de
párrafos (PDF/Word/texto) + reglas EST-001 (RD-01 a RD-04) + persistencia.
"""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

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
from orquestador.pipeline_redaccion import extraer_parrafos, procesar_documento_redaccion

RAIZ = Path(__file__).resolve().parents[2]
RUTA_DOCX_EJEMPLO = RAIZ / "kb" / "plantillas" / "ejemplos" / "EST-001_Guia_Estilo_EJEMPLO.docx"


def _sesion_con_documento_y_analisis(
    contenido: bytes, *, tipo_archivo: str
) -> tuple[Session, Analisis, VersionDocumento]:
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
        nombre_original="texto.txt",
        tipo_archivo=tipo_archivo,
        tamano_bytes=len(contenido),
        area_id=area.id,
        usuario_carga_id=usuario.id,
        fecha_carga=datetime.now(UTC),
        fecha_expiracion=date.today() + timedelta(days=90),
        estado=EstadoDocumento.CARGADO.value,
    )
    tipo_revision = TipoRevision(nombre="redaccion")
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

    version = VersionDocumento(
        documento_id=documento.id,
        numero_version=1,
        ruta_almacenamiento=f"{area.id}/{documento.id}/texto.txt",
        es_corregida=False,
        fecha_creacion=datetime.now(UTC),
    )
    sesion.add(version)
    sesion.commit()

    return sesion, analisis, version


# --- extraer_parrafos ---------------------------------------------------------


def test_extraer_parrafos_divide_texto_plano_por_lineas_en_blanco() -> None:
    contenido = "Primer párrafo.\n\nSegundo párrafo.\n\nTercer párrafo.".encode()
    parrafos = extraer_parrafos("txt", contenido)

    assert [p.texto for p in parrafos] == [
        "Primer párrafo.",
        "Segundo párrafo.",
        "Tercer párrafo.",
    ]
    assert [p.ubicacion for p in parrafos] == ["Párrafo 1", "Párrafo 2", "Párrafo 3"]


def test_extraer_parrafos_texto_vacio_no_da_parrafos() -> None:
    assert extraer_parrafos("txt", b"   \n\n  ") == []


def test_extraer_parrafos_docx_real() -> None:
    parrafos = extraer_parrafos("docx", RUTA_DOCX_EJEMPLO.read_bytes())
    assert len(parrafos) > 0


def test_extraer_parrafos_formato_no_soportado() -> None:
    import pytest

    with pytest.raises(ValueError, match="no soportado"):
        extraer_parrafos("xlsx", b"nada")


# --- procesar_documento_redaccion (fase 1, determinista) ---------------------


def test_procesar_documento_redaccion_detecta_sigla_no_definida() -> None:
    contenido = b"Hay que reportar a la SAT antes de fin de mes."
    sesion, analisis, version = _sesion_con_documento_y_analisis(contenido, tipo_archivo="txt")

    hallazgos, parrafos = procesar_documento_redaccion(
        sesion,
        analisis=analisis,
        version_original=version,
        contenido_original=contenido,
        tipo_archivo="txt",
        tipo_documento="Memo",
    )

    assert len(parrafos) == 1
    assert len(hallazgos) == 1
    assert "SAT" in hallazgos[0].descripcion
    assert hallazgos[0].estado == "pendiente"
    assert hallazgos[0].fuente_citada == "Regla aplicada: EST-001 §4"

    persistidos = sesion.query(Hallazgo).filter_by(analisis_id=analisis.id).all()
    assert len(persistidos) == 1


def test_procesar_documento_redaccion_sin_hallazgos_no_persiste_nada() -> None:
    contenido = b"Este texto no tiene montos, fechas ni siglas raras."
    sesion, analisis, version = _sesion_con_documento_y_analisis(contenido, tipo_archivo="txt")

    hallazgos, _parrafos = procesar_documento_redaccion(
        sesion,
        analisis=analisis,
        version_original=version,
        contenido_original=contenido,
        tipo_archivo="txt",
        tipo_documento="Correo",
    )

    assert hallazgos == []
    assert sesion.query(Hallazgo).filter_by(analisis_id=analisis.id).count() == 0


def test_procesar_documento_redaccion_procedimiento_sin_secciones() -> None:
    contenido = "Esto es un procedimiento sin ninguna sección formal.".encode()
    sesion, analisis, version = _sesion_con_documento_y_analisis(contenido, tipo_archivo="txt")

    hallazgos, _parrafos = procesar_documento_redaccion(
        sesion,
        analisis=analisis,
        version_original=version,
        contenido_original=contenido,
        tipo_archivo="txt",
        tipo_documento="Procedimiento",
    )

    rd01 = [h for h in hallazgos if "secciones obligatorias" in h.descripcion]
    assert len(rd01) == 1
    assert rd01[0].fuente_citada == "Regla aplicada: EST-001 §2"


def test_procesar_documento_redaccion_pdf_real() -> None:
    """Humo: el PDF real de ejemplo (POL-001) no tiene por qué disparar
    ninguna regla RD-01..04, pero el pipeline debe correr sin errores sobre
    un PDF real (no solo texto plano sintético)."""
    ruta_pdf = RAIZ / "kb" / "plantillas" / "ejemplos" / "POL-001_Politica_Cierre_EJEMPLO.pdf"
    contenido = ruta_pdf.read_bytes()
    sesion, analisis, version = _sesion_con_documento_y_analisis(contenido, tipo_archivo="pdf")

    hallazgos, parrafos = procesar_documento_redaccion(
        sesion,
        analisis=analisis,
        version_original=version,
        contenido_original=contenido,
        tipo_archivo="pdf",
        tipo_documento="Procedimiento",
    )

    assert len(parrafos) > 0
    assert isinstance(hallazgos, list)
