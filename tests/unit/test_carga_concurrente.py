"""La lógica de métricas del script de carga (tests/carga/carga_concurrente.py)."""

import importlib.util
import sys
from pathlib import Path

RUTA = Path(__file__).resolve().parents[1] / "carga" / "carga_concurrente.py"
spec = importlib.util.spec_from_file_location("carga_concurrente", RUTA)
carga = importlib.util.module_from_spec(spec)
sys.modules["carga_concurrente"] = carga  # los dataclasses resuelven su módulo aquí
spec.loader.exec_module(carga)


def test_percentil_por_rango_mas_cercano() -> None:
    valores = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]

    assert carga.percentil(valores, 50) == 50.0
    assert carga.percentil(valores, 90) == 90.0
    assert carga.percentil(valores, 100) == 100.0
    assert carga.percentil([7.0], 90) == 7.0
    assert carga.percentil([], 50) is None


def test_resumen_cuenta_fallos_y_calcula_documentos_por_hora() -> None:
    mediciones = [
        carga.Medicion("contable", True, 5.0, 100.0, "completado"),
        carga.Medicion("contable", True, 6.0, 200.0, "completado"),
        carga.Medicion("contable", False, None, None, "excedido", "TimeoutError"),
    ]

    r = carga.resumir(mediciones, duracion_s=360.0, usuarios=3, escenario="contable")

    assert (r["peticiones"], r["ok"], r["fallos"]) == (3, 2, 1)
    assert r["t_total_p50_s"] == 100.0 and r["t_total_max_s"] == 200.0
    assert r["t_primeros_p50_s"] == 5.0
    assert r["docs_por_hora"] == 20.0  # 2 documentos en 6 minutos
    assert r["errores"] == ["TimeoutError"]


def test_resumen_sin_exitos_no_falla() -> None:
    r = carga.resumir([carga.Medicion("chat", False, None, None, "error", "x")], 10.0, 1, "chat")

    assert r["ok"] == 0 and r["t_total_p50_s"] is None and r["docs_por_hora"] == 0.0


def test_tabla_markdown_tiene_una_fila_por_nivel() -> None:
    resumenes = [
        carga.resumir([carga.Medicion("chat", True, 3.0, 3.0, "respondido")], 3.0, n, "chat")
        for n in (1, 3)
    ]

    tabla = carga.tabla_markdown(resumenes)

    assert tabla.count("\n") == 3  # encabezado, separador y dos filas
    assert "| chat | 1 | 1 / 1 |" in tabla and "| chat | 3 | 1 / 1 |" in tabla


def test_el_excel_por_defecto_existe_en_el_repositorio() -> None:
    assert carga.EXCEL_POR_DEFECTO.exists()


def test_la_tabla_muestra_los_estados_finales_y_los_errores() -> None:
    fallida = carga.Medicion("contable", False, None, None, "fallido", "TimeoutError")
    r = carga.resumir([fallida], 327.0, 1, "contable")

    tabla = carga.tabla_markdown([r])

    assert "fallido: 1" in tabla and "TimeoutError" in tabla

