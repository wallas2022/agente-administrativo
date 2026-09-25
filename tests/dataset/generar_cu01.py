"""Genera el dataset sintético de 10 Excel contables para CU-01 (Sprint 1),
con errores sembrados y su hoja de respuestas. Herramienta de datos de
prueba, no código de aplicación — ver docs/04-pruebas/plan-pruebas-prototipo.md
(PP-01) y tests/dataset/README.md.

Uso: .venv/Scripts/python.exe tests/dataset/generar_cu01.py
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from openpyxl import Workbook

RAIZ = Path(__file__).resolve().parent / "cu-01"
CATALOGO_VALIDO = ["1010", "1020", "4010", "5010", "2010"]


@dataclass
class Partida:
    cuenta: str
    descripcion: str
    fecha: date
    debe: float
    haber: float
    moneda: str = "Q"


def _escribir_libro(
    nombre_archivo: str,
    partidas: list[Partida],
    *,
    total_con_formula: bool = True,
) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Partidas"
    ws.append(["Cuenta", "Descripcion", "Fecha", "Debe", "Haber", "Moneda"])
    for p in partidas:
        ws.append([p.cuenta, p.descripcion, p.fecha, p.debe, p.haber, p.moneda])

    fila_total = len(partidas) + 2
    primera_fila = 2
    ultima_fila = len(partidas) + 1
    ws.cell(row=fila_total, column=1, value="TOTAL")
    if total_con_formula:
        ws.cell(row=fila_total, column=4, value=f"=SUM(D{primera_fila}:D{ultima_fila})")
        ws.cell(row=fila_total, column=5, value=f"=SUM(E{primera_fila}:E{ultima_fila})")
    else:
        ws.cell(row=fila_total, column=4, value=round(sum(p.debe for p in partidas), 2))
        ws.cell(row=fila_total, column=5, value=round(sum(p.haber for p in partidas), 2))

    RAIZ.mkdir(parents=True, exist_ok=True)
    wb.save(RAIZ / nombre_archivo)


def _escribir_respuestas(nombre_archivo: str, filas: list[str]) -> None:
    (RAIZ / "respuestas").mkdir(parents=True, exist_ok=True)
    destino = RAIZ / "respuestas" / f"{nombre_archivo.replace('.xlsx', '')}.respuestas.md"
    contenido = "\n".join(
        [
            f"# Hoja de respuestas — {nombre_archivo}",
            "",
            "| # | Regla | Ubicación | Descripción |",
            "| --- | --- | --- | --- |",
            *filas,
            "",
        ]
    )
    destino.write_text(contenido, encoding="utf-8")


def _doc_01_limpio() -> None:
    partidas = [
        Partida("1010", "Cobro cliente A", date(2026, 1, 5), 1000.0, 0.0),
        Partida("4010", "Ingreso servicio A", date(2026, 1, 5), 0.0, 1000.0),
        Partida("1020", "Deposito banco", date(2026, 1, 8), 500.0, 0.0),
        Partida("1010", "Traslado a banco", date(2026, 1, 8), 0.0, 500.0),
    ]
    _escribir_libro("cu01-01-limpio.xlsx", partidas)
    _escribir_respuestas(
        "cu01-01-limpio.xlsx",
        ["| — | — | — | Sin errores sembrados (línea base de falsos positivos) |"],
    )


def _doc_02_descuadre() -> None:
    partidas = [
        Partida("1010", "Cobro cliente B", date(2026, 1, 6), 800.0, 0.0),
        Partida("4010", "Ingreso servicio B", date(2026, 1, 6), 0.0, 750.0),
    ]
    _escribir_libro("cu01-02-descuadre.xlsx", partidas)
    _escribir_respuestas(
        "cu01-02-descuadre.xlsx",
        ["| 1 | RN-01 | Partidas!A3 (fila de totales) | Descuadre de Q50.00 entre debe y haber |"],
    )


def _doc_03_cuenta_inexistente() -> None:
    partidas = [
        Partida("1010", "Cobro cliente C", date(2026, 1, 7), 300.0, 0.0),
        Partida("9999", "Cuenta no catalogada", date(2026, 1, 7), 0.0, 300.0),
    ]
    _escribir_libro("cu01-03-cuenta-inexistente.xlsx", partidas)
    _escribir_respuestas(
        "cu01-03-cuenta-inexistente.xlsx",
        ["| 1 | RN-02 | Partidas!A3 | Cuenta '9999' no existe en el catálogo |"],
    )


def _doc_04_formula_reemplazada() -> None:
    partidas = [
        Partida("1010", "Cobro cliente D", date(2026, 1, 9), 400.0, 0.0),
        Partida("4010", "Ingreso servicio D", date(2026, 1, 9), 0.0, 400.0),
    ]
    _escribir_libro("cu01-04-formula-reemplazada.xlsx", partidas, total_con_formula=False)
    _escribir_respuestas(
        "cu01-04-formula-reemplazada.xlsx",
        [
            "| 1 | RN-FORMULA | Partidas!A4 (fila de totales) | Columnas Debe y Haber de la fila "
            "de totales tienen un valor fijo en vez de fórmula |"
        ],
    )


def _doc_05_fecha_fuera_periodo() -> None:
    partidas = [
        Partida("1010", "Cobro cliente E", date(2026, 1, 10), 200.0, 0.0),
        Partida("4010", "Ingreso servicio E", date(2025, 12, 28), 0.0, 200.0),
    ]
    _escribir_libro("cu01-05-fecha-fuera-periodo.xlsx", partidas)
    _escribir_respuestas(
        "cu01-05-fecha-fuera-periodo.xlsx",
        ["| 1 | RN-03 | Partidas!A3 | Fecha 2025-12-28 fuera del período 2026-01 |"],
    )


def _doc_06_duplicado() -> None:
    partidas = [
        Partida("1010", "Cobro cliente F", date(2026, 1, 11), 600.0, 0.0),
        Partida("1010", "Cobro cliente F", date(2026, 1, 11), 600.0, 0.0),
        Partida("4010", "Ingreso servicio F", date(2026, 1, 11), 0.0, 1200.0),
    ]
    _escribir_libro("cu01-06-duplicado.xlsx", partidas)
    _escribir_respuestas(
        "cu01-06-duplicado.xlsx",
        [
            "| 1 | RN-04 | Partidas!A2 | Posible duplicado de Partidas!A3 (cuenta/monto/fecha) |",
            "| 2 | RN-04 | Partidas!A3 | Posible duplicado de Partidas!A2 (cuenta/monto/fecha) |",
        ],
    )


def _doc_07_mezcla_moneda() -> None:
    partidas = [
        Partida("1010", "Cobro cliente G (Q)", date(2026, 1, 12), 100.0, 0.0, moneda="Q"),
        Partida("1010", "Cobro cliente G (USD)", date(2026, 1, 12), 50.0, 0.0, moneda="USD"),
        Partida("4010", "Ingreso servicio G", date(2026, 1, 12), 0.0, 150.0, moneda="Q"),
    ]
    _escribir_libro("cu01-07-mezcla-moneda.xlsx", partidas)
    _escribir_respuestas(
        "cu01-07-mezcla-moneda.xlsx",
        ["| 1 | RN-05 | Partidas!A2 | Mezcla de monedas Q/USD sin tipo de cambio explícito |"],
    )


def _doc_08_multiples_errores() -> None:
    partidas = [
        Partida("1010", "Cobro cliente H", date(2026, 1, 13), 900.0, 0.0),
        Partida("9998", "Cuenta no catalogada", date(2026, 1, 13), 0.0, 850.0),
    ]
    _escribir_libro("cu01-08-multiples-errores.xlsx", partidas)
    _escribir_respuestas(
        "cu01-08-multiples-errores.xlsx",
        [
            "| 1 | RN-01 | Partidas!A3 (fila de totales) | Descuadre de Q50.00 |",
            "| 2 | RN-02 | Partidas!A3 | Cuenta '9998' no existe en el catálogo |",
        ],
    )


def _doc_09_limpio_grande() -> None:
    partidas = []
    for i in range(1, 26):
        dia = 1 + (i % 27)
        partidas.append(
            Partida("1010", f"Cobro cliente {i}", date(2026, 1, dia), 100.0 * i, 0.0)
        )
        partidas.append(
            Partida("4010", f"Ingreso servicio {i}", date(2026, 1, dia), 0.0, 100.0 * i)
        )
    _escribir_libro("cu01-09-limpio-grande.xlsx", partidas)
    _escribir_respuestas(
        "cu01-09-limpio-grande.xlsx",
        [
            "| — | — | — | Sin errores sembrados "
            "(50 partidas, línea base de falsos positivos en volumen) |"
        ],
    )


def _doc_10_multiples_errores_2() -> None:
    partidas = [
        Partida("1010", "Cobro cliente I", date(2026, 1, 14), 300.0, 0.0, moneda="Q"),
        Partida("1010", "Cobro cliente I", date(2026, 1, 14), 300.0, 0.0, moneda="Q"),
        Partida("4010", "Ingreso servicio I", date(2025, 11, 2), 0.0, 300.0, moneda="USD"),
        Partida("4010", "Ajuste I", date(2026, 1, 14), 0.0, 300.0, moneda="Q"),
    ]
    _escribir_libro("cu01-10-multiples-errores-2.xlsx", partidas)
    _escribir_respuestas(
        "cu01-10-multiples-errores-2.xlsx",
        [
            "| 1 | RN-03 | Partidas!A4 | Fecha 2025-11-02 fuera del período 2026-01 |",
            "| 2 | RN-04 | Partidas!A2 | Posible duplicado de Partidas!A3 |",
            "| 3 | RN-04 | Partidas!A3 | Posible duplicado de Partidas!A2 |",
            "| 4 | RN-05 | Partidas!A2 | Mezcla de monedas Q/USD sin tipo de cambio explícito |",
        ],
    )


def _escribir_linea_base_tiempos() -> None:
    (RAIZ / "respuestas").mkdir(parents=True, exist_ok=True)
    contenido = (
        "documento,tipo,minutos_revision_manual\n"
        "cu01-01-limpio.xlsx,simple,10\n"
        "cu01-02-descuadre.xlsx,simple,15\n"
        "cu01-03-cuenta-inexistente.xlsx,simple,15\n"
        "cu01-04-formula-reemplazada.xlsx,simple,15\n"
        "cu01-05-fecha-fuera-periodo.xlsx,simple,15\n"
        "cu01-06-duplicado.xlsx,simple,15\n"
        "cu01-07-mezcla-moneda.xlsx,simple,20\n"
        "cu01-08-multiples-errores.xlsx,complejo,30\n"
        "cu01-09-limpio-grande.xlsx,complejo,45\n"
        "cu01-10-multiples-errores-2.xlsx,complejo,40\n"
    )
    (RAIZ / "respuestas" / "linea-base-tiempos.csv").write_text(contenido, encoding="utf-8")


def generar_todo() -> None:
    _doc_01_limpio()
    _doc_02_descuadre()
    _doc_03_cuenta_inexistente()
    _doc_04_formula_reemplazada()
    _doc_05_fecha_fuera_periodo()
    _doc_06_duplicado()
    _doc_07_mezcla_moneda()
    _doc_08_multiples_errores()
    _doc_09_limpio_grande()
    _doc_10_multiples_errores_2()
    _escribir_linea_base_tiempos()
    print(f"Generados 10 documentos + respuestas en {RAIZ}")


if __name__ == "__main__":
    generar_todo()
