"""Reglas deterministas de validación contable (RN-01 a RN-05, CU-01).

RN-01 reporta tanto el descuadre global del documento como, si el archivo
trae la columna opcional "Asiento" (7ma columna del Excel), el descuadre de
cada asiento individual. RN-05 reporta cada partida cuya moneda difiere de
la principal del documento (la más frecuente).

RNF-03: todo cálculo numérico (cuadre, totales, comparaciones) lo hace este
código, nunca el LLM. El LLM solo redacta la explicación en lenguaje natural
a partir de estos hallazgos ya calculados (ver src/api o el orquestador,
`explicacion.py`) — este módulo no hace ninguna llamada al LLM ni convierte
montos entre monedas (no calcula tipo de cambio).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from parsers.excel import LibroContable, PartidaContable


@dataclass(frozen=True)
class HallazgoDetectado:
    regla_codigo: str
    severidad: str  # "alta" | "media" | "baja"
    hoja: str
    fila: int
    ubicacion: str  # "Hoja!A{fila}"
    descripcion: str
    monto: float | None = None
    moneda: str | None = None


def _ubicacion(hoja: str, fila: int) -> str:
    return f"{hoja}!A{fila}"


def _validar_cuadre(libro: LibroContable) -> list[HallazgoDetectado]:
    total_debe = sum(p.debe for p in libro.partidas)
    total_haber = sum(p.haber for p in libro.partidas)
    diferencia = round(total_debe - total_haber, 2)
    if diferencia == 0:
        return []

    hoja = libro.partidas[0].hoja if libro.partidas else (
        libro.fila_total.hoja if libro.fila_total else ""
    )
    fila = libro.fila_total.fila if libro.fila_total else (
        libro.partidas[-1].fila if libro.partidas else 0
    )
    return [
        HallazgoDetectado(
            regla_codigo="RN-01",
            severidad="alta",
            hoja=hoja,
            fila=fila,
            ubicacion=_ubicacion(hoja, fila),
            descripcion=(
                f"Descuadre: total debe ({total_debe:.2f}) no coincide con "
                f"total haber ({total_haber:.2f})"
            ),
            monto=abs(diferencia),
        )
    ]


def _validar_cuadre_por_asiento(libro: LibroContable) -> list[HallazgoDetectado]:
    """Adicional a `_validar_cuadre` (descuadre global): si el archivo trae
    la columna opcional "Asiento", reporta también cada asiento individual
    cuyo debe y haber no coinciden -- una fila por partida del asiento
    afectado, igual que `_validar_duplicados`. Los archivos sin esa columna
    (formato previo, sigue siendo válido) no generan nada aquí y dependen
    solo del chequeo global."""
    grupos: dict[str, list[PartidaContable]] = defaultdict(list)
    for p in libro.partidas:
        if p.asiento:
            grupos[p.asiento].append(p)

    hallazgos = []
    for numero_asiento, partidas_del_asiento in grupos.items():
        total_debe = round(sum(p.debe for p in partidas_del_asiento), 2)
        total_haber = round(sum(p.haber for p in partidas_del_asiento), 2)
        if total_debe == total_haber:
            continue
        for p in partidas_del_asiento:
            hallazgos.append(
                HallazgoDetectado(
                    regla_codigo="RN-01",
                    severidad="alta",
                    hoja=p.hoja,
                    fila=p.fila,
                    ubicacion=_ubicacion(p.hoja, p.fila),
                    descripcion=(
                        f"Descuadre en el asiento {numero_asiento}: total debe "
                        f"({total_debe:.2f}) no coincide con total haber ({total_haber:.2f})"
                    ),
                    monto=round(abs(total_debe - total_haber), 2),
                )
            )
    return hallazgos


def _validar_formula_total(libro: LibroContable) -> list[HallazgoDetectado]:
    if libro.fila_total is None:
        return []
    hallazgos = []
    ft = libro.fila_total
    columnas_no_formula = []
    if not ft.debe_es_formula:
        columnas_no_formula.append("Debe")
    if not ft.haber_es_formula:
        columnas_no_formula.append("Haber")
    if columnas_no_formula:
        hallazgos.append(
            HallazgoDetectado(
                regla_codigo="RN-FORMULA",
                severidad="media",
                hoja=ft.hoja,
                fila=ft.fila,
                ubicacion=_ubicacion(ft.hoja, ft.fila),
                descripcion=(
                    f"La fila de totales tiene columna(s) {', '.join(columnas_no_formula)} "
                    "con un valor fijo en vez de una fórmula de suma"
                ),
            )
        )
    return hallazgos


def _validar_cuentas(libro: LibroContable, catalogo: set[str]) -> list[HallazgoDetectado]:
    return [
        HallazgoDetectado(
            regla_codigo="RN-02",
            severidad="alta",
            hoja=p.hoja,
            fila=p.fila,
            ubicacion=_ubicacion(p.hoja, p.fila),
            descripcion=f"La cuenta '{p.cuenta}' no existe en el catálogo de cuentas vigente",
        )
        for p in libro.partidas
        if p.cuenta not in catalogo
    ]


def _validar_periodo(libro: LibroContable, periodo: tuple[int, int]) -> list[HallazgoDetectado]:
    anio, mes = periodo
    hallazgos = []
    for p in libro.partidas:
        if p.fecha is None:
            continue
        if (p.fecha.year, p.fecha.month) != (anio, mes):
            hallazgos.append(
                HallazgoDetectado(
                    regla_codigo="RN-03",
                    severidad="media",
                    hoja=p.hoja,
                    fila=p.fila,
                    ubicacion=_ubicacion(p.hoja, p.fila),
                    descripcion=(
                        f"La partida tiene fecha {p.fecha.isoformat()}, fuera del "
                        f"período {anio}-{mes:02d} que se está revisando"
                    ),
                )
            )
    return hallazgos


def _validar_duplicados(libro: LibroContable) -> list[HallazgoDetectado]:
    grupos: dict[tuple, list[PartidaContable]] = defaultdict(list)
    for p in libro.partidas:
        grupos[(p.cuenta, p.debe, p.haber, p.fecha)].append(p)

    hallazgos = []
    for partidas_del_grupo in grupos.values():
        if len(partidas_del_grupo) < 2:
            continue
        for p in partidas_del_grupo:
            hallazgos.append(
                HallazgoDetectado(
                    regla_codigo="RN-04",
                    severidad="media",
                    hoja=p.hoja,
                    fila=p.fila,
                    ubicacion=_ubicacion(p.hoja, p.fila),
                    descripcion=(
                        f"Posible partida duplicada: misma cuenta ({p.cuenta}), monto y "
                        f"fecha que otra(s) {len(partidas_del_grupo) - 1} fila(s)"
                    ),
                )
            )
    return hallazgos


def _moneda_principal(partidas: list[PartidaContable]) -> str | None:
    """Moneda con más partidas del documento; un empate se resuelve a favor
    de la que aparece primero (orden estable, sin depender del alfabeto)."""
    conteos: dict[str, int] = {}
    orden_aparicion: list[str] = []
    for p in partidas:
        if not p.moneda:
            continue
        if p.moneda not in conteos:
            orden_aparicion.append(p.moneda)
        conteos[p.moneda] = conteos.get(p.moneda, 0) + 1
    if not orden_aparicion:
        return None
    return max(orden_aparicion, key=lambda m: conteos[m])


def _validar_mezcla_moneda(libro: LibroContable) -> list[HallazgoDetectado]:
    """Reporta cada partida cuya moneda difiere de la principal del
    documento (la más frecuente) -- una fila por partida afectada, en vez
    de un único aviso genérico, para que quede claro cuál(es) partida(s)
    revisar."""
    monedas = {p.moneda for p in libro.partidas if p.moneda}
    if len(monedas) <= 1:
        return []
    principal = _moneda_principal(libro.partidas)
    return [
        HallazgoDetectado(
            regla_codigo="RN-05",
            severidad="alta",
            hoja=p.hoja,
            fila=p.fila,
            ubicacion=_ubicacion(p.hoja, p.fila),
            descripcion=(
                f"Esta partida usa moneda {p.moneda}, distinta de la moneda principal "
                f"del documento ({principal}), sin un tipo de cambio explícito registrado"
            ),
            monto=(p.debe or p.haber) or None,
            moneda=p.moneda,
        )
        for p in libro.partidas
        if p.moneda and p.moneda != principal
    ]


def validar_libro_contable(
    libro: LibroContable, *, catalogo: set[str], periodo: tuple[int, int]
) -> list[HallazgoDetectado]:
    return [
        *_validar_cuadre(libro),
        *_validar_cuadre_por_asiento(libro),
        *_validar_formula_total(libro),
        *_validar_cuentas(libro, catalogo),
        *_validar_periodo(libro, periodo),
        *_validar_duplicados(libro),
        *_validar_mezcla_moneda(libro),
    ]
