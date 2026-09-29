import io
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from comun.modelos import Area, ChecklistCierre, CuentaContable, FuenteConocimiento, Glosario, Regla
from comun.modelos import Base as ModelosBase
from curaduria.plantilla import (
    HOJA_CATALOGO,
    HOJA_CHECKLIST,
    HOJA_FUENTES,
    HOJA_GLOSARIO,
    HOJA_REGLAS,
    cargar_plantilla,
    leer_plantilla,
)

RAIZ = Path(__file__).resolve().parents[2]
RUTA_PLANTILLA_REAL = RAIZ / "kb" / "plantillas" / "Plantilla_Base_Conocimiento_SFC.xlsx"

_FILAS_FUENTES_OK = [
    ("CAT-001", "Catálogo de cuentas", "catálogo (Excel)", "1.0", "2026-01-01", "vigente",
     "Jefatura de Contabilidad", 'hoja "Catálogo de cuentas"', None),
    ("POL-001", "Política de cierre", "política (Word)", "1.0", "2026-01-15", "vigente",
     "Jefatura de Contabilidad", "POL-001.docx", None),
]
_FILAS_CATALOGO_OK = [("1101", "Caja general", "activo", "deudora", "Sí", None)]
_FILAS_REGLAS_OK = [
    ("RN-01", "Cuadre debe/haber", "Contabilidad", "Excel", "alta", "Q", "POL-001 §3", "Sí")
]
_FILAS_GLOSARIO_OK = [
    ("SFC", "Servicios Financieros Compartidos", "General", "CAT-001", "2026-01-01")
]
_FILAS_CHECKLIST_OK = [
    (1, "Conciliaciones bancarias completas", "Tesorería", "Día 2", "Conciliación")
]


def _libro(
    *,
    columnas_fuentes: tuple[str, ...] | None = None,
    filas_fuentes: list[tuple] | None = None,
    filas_catalogo: list[tuple] | None = None,
    filas_reglas: list[tuple] | None = None,
    filas_glosario: list[tuple] | None = None,
    filas_checklist: list[tuple] | None = None,
    omitir_hoja: str | None = None,
) -> bytes:
    """Construye una plantilla mínima válida en memoria, con la misma forma
    que la real (título en fila 1, descripción en fila 2, fila 3 en blanco,
    encabezados en la fila 4, datos desde la fila 5) -- para probar casos de
    error sin depender de mutar el archivo real."""
    columnas_fuentes = columnas_fuentes or (
        "fuente_id", "titulo", "tipo", "version", "vigente_desde", "estado",
        "dueno_area", "archivo_entregado", "observaciones",
    )
    especificacion = {
        HOJA_FUENTES: (
            columnas_fuentes,
            filas_fuentes if filas_fuentes is not None else _FILAS_FUENTES_OK,
        ),
        HOJA_CATALOGO: (
            ("codigo", "nombre", "tipo", "naturaleza", "acepta_movimiento", "notas"),
            filas_catalogo if filas_catalogo is not None else _FILAS_CATALOGO_OK,
        ),
        HOJA_REGLAS: (
            ("id_regla", "descripcion", "area", "tipo_documento", "severidad", "moneda",
             "fuente_id", "estado_validacion"),
            filas_reglas if filas_reglas is not None else _FILAS_REGLAS_OK,
        ),
        HOJA_GLOSARIO: (
            ("termino", "definicion", "area", "fuente_id", "vigente_desde"),
            filas_glosario if filas_glosario is not None else _FILAS_GLOSARIO_OK,
        ),
        HOJA_CHECKLIST: (
            ("n", "actividad", "responsable", "plazo", "evidencia_requerida"),
            filas_checklist if filas_checklist is not None else _FILAS_CHECKLIST_OK,
        ),
    }

    wb = Workbook()
    wb.remove(wb.active)
    for nombre_hoja, (columnas, filas) in especificacion.items():
        if nombre_hoja == omitir_hoja:
            continue
        ws = wb.create_sheet(nombre_hoja)
        ws.append((nombre_hoja,))
        ws.append(("Descripción de prueba",))
        ws.append(())
        ws.append(columnas)
        for fila in filas:
            ws.append(fila)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _sesion_en_memoria() -> Session:
    engine = create_engine("sqlite:///:memory:")
    ModelosBase.metadata.create_all(engine)
    return Session(engine)


# --- leer_plantilla: camino feliz (archivo real) ---------------------------


def test_leer_plantilla_real_es_valida_y_cuenta_todas_las_filas() -> None:
    resultado = leer_plantilla(str(RUTA_PLANTILLA_REAL))

    assert resultado.es_valido, [str(e) for e in resultado.errores]
    assert len(resultado.fuentes) == 8
    assert len(resultado.cuentas) == 42
    assert len(resultado.reglas) == 14
    assert len(resultado.glosario) == 16
    assert len(resultado.checklist) == 12


def test_leer_plantilla_real_parsea_fuente_id_y_cita_de_reglas() -> None:
    resultado = leer_plantilla(str(RUTA_PLANTILLA_REAL))

    rn01 = next(r for r in resultado.reglas if r.id_regla == "RN-01")
    assert rn01.fuente_id == "POL-001"
    assert rn01.cita == "§3"

    rn02 = next(r for r in resultado.reglas if r.id_regla == "RN-02")
    assert rn02.fuente_id == "CAT-001"
    assert rn02.cita == ""

    # RN-06 cita dos fuentes ("EST-001, GLO-001") -- se toma la primera como
    # fuente_id principal y el resto queda en la cita (sin fallar ni perder
    # la referencia a GLO-001, aunque no se use como FK).
    rn06 = next(r for r in resultado.reglas if r.id_regla == "RN-06")
    assert rn06.fuente_id == "EST-001"
    assert "GLO-001" in rn06.cita


# --- leer_plantilla: camino feliz mínimo ------------------------------------


def test_leer_plantilla_minima_valida() -> None:
    resultado = leer_plantilla(_libro())
    assert resultado.es_valido, [str(e) for e in resultado.errores]
    assert len(resultado.fuentes) == 2
    assert len(resultado.cuentas) == 1
    assert len(resultado.reglas) == 1
    assert len(resultado.glosario) == 1
    assert len(resultado.checklist) == 1


# --- errores: hojas y columnas ---------------------------------------------


def test_leer_plantilla_reporta_hoja_faltante() -> None:
    resultado = leer_plantilla(_libro(omitir_hoja=HOJA_CHECKLIST))
    assert not resultado.es_valido
    assert any("Checklist de cierre" in str(e) for e in resultado.errores)


def test_leer_plantilla_reporta_columna_faltante_sin_intentar_leer_filas() -> None:
    resultado = leer_plantilla(_libro(columnas_fuentes=("fuente_id", "titulo")))
    assert not resultado.es_valido
    assert any(
        e.hoja == HOJA_FUENTES and "columnas requeridas" in e.mensaje for e in resultado.errores
    )
    assert resultado.fuentes == []


# --- errores: códigos únicos -------------------------------------------------


def test_leer_plantilla_reporta_fuente_id_duplicado() -> None:
    filas = [*_FILAS_FUENTES_OK, _FILAS_FUENTES_OK[0]]
    resultado = leer_plantilla(_libro(filas_fuentes=filas))
    assert not resultado.es_valido
    assert any("duplicado" in e.mensaje and e.columna == "fuente_id" for e in resultado.errores)


def test_leer_plantilla_reporta_codigo_de_cuenta_duplicado() -> None:
    filas = [*_FILAS_CATALOGO_OK, _FILAS_CATALOGO_OK[0]]
    resultado = leer_plantilla(_libro(filas_catalogo=filas))
    assert not resultado.es_valido
    assert any("duplicado" in e.mensaje and e.columna == "codigo" for e in resultado.errores)


# --- errores: estados/naturaleza válidos ------------------------------------


def test_leer_plantilla_reporta_naturaleza_invalida() -> None:
    filas = [("1101", "Caja general", "activo", "neutra", "Sí", None)]
    resultado = leer_plantilla(_libro(filas_catalogo=filas))
    assert not resultado.es_valido
    assert any(e.columna == "naturaleza" for e in resultado.errores)


def test_leer_plantilla_reporta_acepta_movimiento_invalido() -> None:
    filas = [("1101", "Caja general", "activo", "deudora", "tal vez", None)]
    resultado = leer_plantilla(_libro(filas_catalogo=filas))
    assert not resultado.es_valido
    assert any(e.columna == "acepta_movimiento" for e in resultado.errores)


def test_leer_plantilla_reporta_estado_de_fuente_invalido() -> None:
    filas = [
        ("POL-001", "Política de cierre", "política (Word)", "1.0", "2026-01-15", "publicado",
         "Jefatura de Contabilidad", "POL-001.docx", None)
    ]
    resultado = leer_plantilla(_libro(filas_fuentes=filas))
    assert not resultado.es_valido
    assert any(e.columna == "estado" for e in resultado.errores)


# --- errores: fechas ---------------------------------------------------------


def test_leer_plantilla_reporta_fecha_invalida() -> None:
    filas = [
        ("POL-001", "Política de cierre", "política (Word)", "1.0", "15 de enero", "vigente",
         "Jefatura de Contabilidad", "POL-001.docx", None)
    ]
    resultado = leer_plantilla(_libro(filas_fuentes=filas))
    assert not resultado.es_valido
    assert any(e.columna == "vigente_desde" for e in resultado.errores)


# --- errores: referencias cruzadas de fuente_id -----------------------------


def test_leer_plantilla_reporta_fuente_id_de_regla_inexistente_en_inventario() -> None:
    filas = [("RN-99", "Regla nueva", "Contabilidad", "Excel", "alta", "Q", "ZZZ-999", "Sí")]
    resultado = leer_plantilla(_libro(filas_reglas=filas))
    assert not resultado.es_valido
    assert any("ZZZ-999" in e.mensaje for e in resultado.errores)


def test_leer_plantilla_reporta_fuente_id_de_glosario_inexistente_en_inventario() -> None:
    filas = [("XYZ", "Definición", "General", "ZZZ-999", "2026-01-01")]
    resultado = leer_plantilla(_libro(filas_glosario=filas))
    assert not resultado.es_valido
    assert any("ZZZ-999" in e.mensaje for e in resultado.errores)


# --- reúne todos los errores, no se detiene en el primero -------------------


def test_leer_plantilla_reune_errores_de_varias_hojas_a_la_vez() -> None:
    resultado = leer_plantilla(
        _libro(
            filas_catalogo=[("1101", "Caja general", "activo", "neutra", "Sí", None)],
            filas_checklist=[("no-es-numero", "Actividad", "Tesorería", "Día 2", "Evidencia")],
        )
    )
    hojas_con_error = {e.hoja for e in resultado.errores}
    assert HOJA_CATALOGO in hojas_con_error
    assert HOJA_CHECKLIST in hojas_con_error


# --- cargar_plantilla: se niega a cargar con errores -------------------------


def test_cargar_plantilla_se_niega_si_hay_errores() -> None:
    resultado = leer_plantilla(_libro(omitir_hoja=HOJA_CHECKLIST))
    sesion = _sesion_en_memoria()
    with pytest.raises(ValueError, match="errores"):
        cargar_plantilla(
            sesion,
            resultado,
            area_id_por_defecto=uuid.uuid4(),
            cargado_por=uuid.uuid4(),
            ahora=datetime.now(UTC),
        )


# --- cargar_plantilla: persiste todo como borrador --------------------------


def test_cargar_plantilla_real_persiste_todo_como_borrador_y_enlaza_fuente_id() -> None:
    resultado = leer_plantilla(str(RUTA_PLANTILLA_REAL))
    assert resultado.es_valido

    sesion = _sesion_en_memoria()
    area = Area(nombre="Contabilidad")
    sesion.add(area)
    sesion.flush()
    usuario_id = uuid.uuid4()

    resumen = cargar_plantilla(
        sesion,
        resultado,
        area_id_por_defecto=area.id,
        cargado_por=usuario_id,
        ahora=datetime.now(UTC),
        contenido_plantilla=RUTA_PLANTILLA_REAL.read_bytes(),
    )

    assert resumen == {"fuentes": 8, "cuentas": 42, "reglas": 14, "glosario": 16, "checklist": 12}

    fuentes = sesion.query(FuenteConocimiento).all()
    assert len(fuentes) == 8
    assert all(f.estado == "borrador" for f in fuentes)
    assert all(f.cargado_por == usuario_id for f in fuentes)
    assert all(f.tipo == "regla_interna" for f in fuentes)  # sin ejemplos normativa/referencia

    cat_001 = next(f for f in fuentes if f.fuente_id == "CAT-001")
    assert cat_001.sha256 is not None  # hoja embebida -> hash de la propia plantilla
    pol_001 = next(f for f in fuentes if f.fuente_id == "POL-001")
    assert pol_001.sha256 is None  # documento externo, no adjuntado en esta carga

    assert sesion.query(CuentaContable).count() == 42
    caja = sesion.query(CuentaContable).filter_by(codigo="1101").one()
    assert caja.fuente_id == cat_001.id
    assert caja.acepta_movimiento is True

    assert sesion.query(Regla).count() == 14
    rn01 = sesion.query(Regla).filter_by(codigo="RN-01").one()
    assert rn01.fuente_id == pol_001.id
    assert rn01.estado == "borrador"

    assert sesion.query(Glosario).count() == 16
    sfc = sesion.query(Glosario).filter_by(termino="SFC").one()
    glo_001 = next(f for f in fuentes if f.fuente_id == "GLO-001")
    assert sfc.fuente_id == glo_001.id

    assert sesion.query(ChecklistCierre).count() == 12
    chk_001 = next(f for f in fuentes if f.fuente_id == "CHK-001")
    primera_actividad = sesion.query(ChecklistCierre).filter_by(numero=1).one()
    assert primera_actividad.fuente_id == chk_001.id
