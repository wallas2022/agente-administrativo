import io
from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook

from parsers.excel import TablaContableNoDetectadaError, leer_libro_contable

RAIZ_ESCENARIOS_USUARIO = Path(__file__).resolve().parents[1] / "dataset" / "escenarios-usuario"


def _libro_de_prueba(*, fila_total_con_formula: bool) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Partidas"
    ws.append(["Cuenta", "Descripcion", "Fecha", "Debe", "Haber", "Moneda"])
    ws.append(["1010", "Cobro cliente A", date(2026, 1, 5), 1000.00, 0.00, "Q"])
    ws.append(["4010", "Ingreso servicio A", date(2026, 1, 5), 0.00, 1000.00, "Q"])
    ws.append(["1010", "Cobro cliente B", date(2026, 1, 10), 500.00, 0.00, "Q"])
    ws.append(["4010", "Ingreso servicio B", date(2026, 1, 10), 0.00, 500.00, "Q"])

    fila_total = 6
    if fila_total_con_formula:
        ws.cell(row=fila_total, column=1, value="TOTAL")
        ws.cell(row=fila_total, column=4, value="=SUM(D2:D5)")
        ws.cell(row=fila_total, column=5, value="=SUM(E2:E5)")
    else:
        ws.cell(row=fila_total, column=1, value="TOTAL")
        ws.cell(row=fila_total, column=4, value=1500.00)  # valor fijo, no fórmula
        ws.cell(row=fila_total, column=5, value=1500.00)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def test_leer_libro_extrae_las_partidas_con_ubicacion() -> None:
    libro = leer_libro_contable(io.BytesIO(_libro_de_prueba(fila_total_con_formula=True)))

    assert len(libro.partidas) == 4
    primera = libro.partidas[0]
    assert primera.hoja == "Partidas"
    assert primera.fila == 2
    assert primera.cuenta == "1010"
    assert primera.debe == 1000.00
    assert primera.moneda == "Q"


def test_leer_libro_detecta_si_la_fila_total_es_formula() -> None:
    libro_con_formula = leer_libro_contable(
        io.BytesIO(_libro_de_prueba(fila_total_con_formula=True))
    )
    libro_sin_formula = leer_libro_contable(
        io.BytesIO(_libro_de_prueba(fila_total_con_formula=False))
    )

    assert libro_con_formula.fila_total is not None
    assert libro_con_formula.fila_total.debe_es_formula is True
    assert libro_con_formula.fila_total.haber_es_formula is True

    assert libro_sin_formula.fila_total is not None
    assert libro_sin_formula.fila_total.debe_es_formula is False
    assert libro_sin_formula.fila_total.haber_es_formula is False


# --- Detector de tabla "cualquier formato" (CU-01, Bloque 1) ----------------


def _guardar(wb: Workbook) -> bytes:
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def test_detecta_encabezado_con_titulo_combinado_fila_vacia_y_orden_de_columnas_distinto() -> None:
    """Replica el layout real de Libro_Diario_Ejercicio_Contable_con_Errores
    .xlsx: título en una celda combinada (fila 1), fila 2 vacía, encabezado
    en fila 3 con nombres y orden distintos al formato fijo, sin columna
    Moneda, código de cuenta como número."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Libro Diario"
    ws.append(["Mi Empresa, S.A. - Libro Diario", None, None, None, None, None, None])
    ws.merge_cells("A1:G1")
    ws.append([None] * 7)
    ws.append(
        ["Fecha", "N° Asiento", "Código de Cuenta", "Cuenta / Concepto", "Debe", "Haber", "Notas"]
    )
    ws.append([date(2026, 5, 1), "Asiento 1", 1101, "Bancos", 500000.0, None, None])
    ws.append([date(2026, 5, 1), "Asiento 1", 3101, "Capital Social", None, 500000.0, None])
    ws.append([None, None, None, "SUMA TOTAL", 500000.0, 500000.0, None])

    libro = leer_libro_contable(io.BytesIO(_guardar(wb)))

    assert len(libro.partidas) == 2
    primera = libro.partidas[0]
    assert primera.cuenta == "1101"  # texto limpio, sin ".0"
    assert primera.descripcion == "Bancos"
    assert primera.fecha == date(2026, 5, 1)
    assert primera.debe == 500000.0
    assert primera.moneda == "Q"  # sin columna Moneda ni marca (Q)/($): Q por defecto
    assert primera.asiento == "Asiento 1"
    assert libro.fila_total is not None
    assert libro.fila_total.fila == 6  # "SUMA TOTAL" detectado aunque esté en la columna D, no la A


def test_detecta_moneda_por_defecto_desde_el_encabezado() -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(["Cuenta", "Descripcion", "Debe (Q)", "Haber (Q)"])
    ws.append(["1010", "Cobro", 100.0, 0.0])

    libro = leer_libro_contable(io.BytesIO(_guardar(wb)))

    assert libro.partidas[0].moneda == "Q"


def test_fin_de_tabla_por_fila_vacia_sin_fila_de_totales() -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(["Cuenta", "Descripcion", "Debe", "Haber"])
    ws.append(["1010", "Cobro", 100.0, 0.0])
    ws.append([None, None, None, None])
    ws.append(["9999", "No debería leerse", 1.0, 1.0])  # después de la fila vacía: se ignora

    libro = leer_libro_contable(io.BytesIO(_guardar(wb)))

    assert len(libro.partidas) == 1
    assert libro.fila_total is None


def test_recorre_todas_las_hojas_hasta_encontrar_una_tabla_valida() -> None:
    wb = Workbook()
    hoja_notas = wb.active
    hoja_notas.title = "Notas"
    hoja_notas.append(["Asiento", "Cuenta", "Concepto"])  # sin Debe/Haber: no es la tabla
    hoja_notas.append(["Asiento 1", "1010", "Cobro"])

    hoja_partidas = wb.create_sheet("Partidas")
    hoja_partidas.append(["Cuenta", "Descripcion", "Debe", "Haber"])
    hoja_partidas.append(["1010", "Cobro", 100.0, 0.0])

    libro = leer_libro_contable(io.BytesIO(_guardar(wb)))

    assert len(libro.partidas) == 1
    assert libro.partidas[0].hoja == "Partidas"


def test_sin_tabla_reconocible_en_ninguna_hoja_levanta_error_claro() -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(["Columna A", "Columna B"])
    ws.append(["x", "y"])

    with pytest.raises(TablaContableNoDetectadaError):
        leer_libro_contable(io.BytesIO(_guardar(wb)))


_ARCHIVO_LIBRO_DIARIO_REAL = "Libro_Diario_Ejercicio_Contable_con_Errores.xlsx"


@pytest.mark.skipif(
    not (RAIZ_ESCENARIOS_USUARIO / _ARCHIVO_LIBRO_DIARIO_REAL).exists(),
    reason="escenario de usuario no disponible",
)
def test_lee_el_libro_diario_real_sin_convertirlo_a_mano() -> None:
    """Archivo real de un usuario (no sintético, no pre-adaptado al formato
    fijo): título combinado, fila en blanco, encabezado en fila 3 con
    nombres/orden distintos ("Código de Cuenta", "Cuenta / Concepto", sin
    columna Moneda), código de cuenta como número, "SUMA TOTAL" en la
    columna de descripción. Antes de este bloque, alguien tenía que
    convertir este archivo a mano (ver Libro_Diario_Mayo2026_formato_
    agente.xlsx) antes de poder correr el pipeline."""
    libro = leer_libro_contable(str(RAIZ_ESCENARIOS_USUARIO / _ARCHIVO_LIBRO_DIARIO_REAL))

    assert len(libro.partidas) == 9
    assert all(p.moneda == "Q" for p in libro.partidas)
    assert all("." not in p.cuenta or p.cuenta.count(".") > 1 for p in libro.partidas)
    assert libro.fila_total is not None
    assert libro.fila_total.debe_declarado == 995000.0
    assert libro.fila_total.haber_declarado == 985000.0

    asiento_3 = [p for p in libro.partidas if p.asiento == "Asiento 3"]
    assert round(sum(p.debe for p in asiento_3) - sum(p.haber for p in asiento_3), 2) == 10000.0
