import io

from openpyxl import Workbook, load_workbook

from parsers.correcciones import CorreccionAplicable
from parsers.xlsx import aplicar_correcciones_xlsx, leer_texto_xlsx


def _libro_de_prueba() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Descripciones"
    ws.append(["Código", "Descripción"])
    ws.append(["1020", "Bancos, cuentas monetarias"])
    ws.append([100, "Gastos de papelería"])  # A3 numérico: no debe extraerse
    ws.cell(row=4, column=1, value="=A2")  # fórmula que evalúa a texto: excluir igual
    ws.cell(row=4, column=1).data_type = "f"
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def test_extrae_celdas_de_texto_con_su_coordenada() -> None:
    segmentos = leer_texto_xlsx(io.BytesIO(_libro_de_prueba()))

    por_ubicacion = {s.ubicacion: s.texto for s in segmentos}
    assert por_ubicacion["Descripciones!A1"] == "Código"
    assert por_ubicacion["Descripciones!B2"] == "Bancos, cuentas monetarias"


def test_no_extrae_celdas_numericas() -> None:
    segmentos = leer_texto_xlsx(io.BytesIO(_libro_de_prueba()))

    assert not any(s.ubicacion == "Descripciones!A3" for s in segmentos)


def test_no_extrae_celdas_con_formula() -> None:
    segmentos = leer_texto_xlsx(io.BytesIO(_libro_de_prueba()))

    assert not any(s.ubicacion == "Descripciones!A4" for s in segmentos)


def test_aplicar_correccion_reemplaza_subcadena_de_la_celda() -> None:
    correccion = CorreccionAplicable("Descripciones!B2", "Bancos", "Bancos S.A.")

    resultado = aplicar_correcciones_xlsx(io.BytesIO(_libro_de_prueba()), [correccion])

    assert resultado.no_aplicadas == []
    libro = load_workbook(io.BytesIO(resultado.contenido))
    assert libro["Descripciones"]["B2"].value == "Bancos S.A., cuentas monetarias"


def test_correccion_en_celda_o_texto_inexistente_queda_en_no_aplicadas() -> None:
    correccion_celda_vacia = CorreccionAplicable("Descripciones!Z99", "algo", "otro")
    correccion_texto_distinto = CorreccionAplicable("Descripciones!A1", "texto que no está", "x")

    resultado = aplicar_correcciones_xlsx(
        io.BytesIO(_libro_de_prueba()), [correccion_celda_vacia, correccion_texto_distinto]
    )

    assert resultado.no_aplicadas == [correccion_celda_vacia, correccion_texto_distinto]
