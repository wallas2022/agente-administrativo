"""Parser de Excel contable (RF-06, CU-01). Detecta la tabla de partidas en
cualquier hoja/formato razonable (no asume una plantilla fija de columnas) y
detecta si la fila de totales usa fórmula o un valor fijo (RN: "fórmula
reemplazada por valor"). Sin lógica de validación aquí -- solo lectura y
normalización; las reglas de negocio viven en `validadores.contable`.

Detección de tabla (Bloque 1 de la tarea "CU-01: leer cualquier tabla"):
se busca, hoja por hoja, una fila de encabezado reconocible por sinónimos de
cada columna (Debe/Haber/Cuenta/Descripción/Fecha/Asiento) en vez de asumir
que la fila 1 siempre trae exactamente "Cuenta|Descripcion|Fecha|Debe|Haber|
Moneda" en ese orden -- ver `_detectar_encabezado`. Si ninguna hoja tiene una
fila así, se levanta `TablaContableNoDetectadaError` (una futura pantalla de
mapeo de columnas, todavía no implementada, podrá ofrecerle al usuario
corregir el mapeo a mano en vez de solo fallar).
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

CUENTA_TOTAL = "TOTAL"

# Cuántas filas desde el inicio de cada hoja se revisan buscando el
# encabezado -- un documento real trae a lo más un título y un par de filas
# en blanco antes de la tabla (ver Libro_Diario_Ejercicio_Contable_con_
# Errores.xlsx: título en fila 1, vacía en fila 2, encabezado en fila 3).
# Un límite evita escanear hojas enteras (o reportes/leyendas al final del
# documento) buscando algo que nunca va a aparecer tan abajo.
MAX_FILAS_BUSQUEDA_ENCABEZADO = 30

# Sinónimos por rol de columna (ya normalizados: sin acentos, en minúscula,
# comparados por token completo -- no por substring, para no confundir
# "Notas" con "No." ni "Cuenta por Cobrar" dentro de una leyenda con el
# encabezado real). "cuenta" es una señal débil a propósito: por sí sola es
# ambigua (puede ser el código de cuenta o, como en "Cuenta / Concepto", el
# nombre) -- solo se usa como respaldo si ninguna celda trae la señal fuerte
# "código" Y la celda no quedó asignada ya a otro rol (ver _detectar_encabezado).
_SINONIMOS_DEBE = frozenset({"debe", "cargo", "debito"})
_SINONIMOS_HABER = frozenset({"haber", "abono", "credito"})
_SINONIMOS_CUENTA_FUERTE = frozenset({"codigo"})
_SINONIMOS_CUENTA_DEBIL = frozenset({"cuenta"})
# "concepto" no estaba en el pedido original (nombre/descripción) pero es el
# término real que usa Libro_Diario_Ejercicio_Contable_con_Errores.xlsx
# ("Cuenta / Concepto") -- sin él, esa columna no calzaría con ningún rol.
_SINONIMOS_DESCRIPCION = frozenset({"nombre", "descripcion", "concepto"})
_SINONIMOS_FECHA = frozenset({"fecha"})
# "no" (de "N° Asiento" o una columna suelta "No.") es una señal corta y
# algo arriesgada, pero al comparar por token completo (no substring) no
# choca con "Notas" (tokeniza aparte, como "notas") -- límite conocido: sí
# chocaría con una columna real llamada exactamente "No" para otra cosa.
_SINONIMOS_ASIENTO = frozenset({"asiento", "partida", "no"})
_SINONIMOS_MONEDA = frozenset({"moneda"})

_PATRON_TOKEN = re.compile(r"[a-z0-9]+")


class TablaContableNoDetectadaError(Exception):
    """Ninguna hoja del archivo tiene una fila reconocible como encabezado
    de libro contable (ver `_detectar_encabezado`)."""


@dataclass(frozen=True)
class PartidaContable:
    hoja: str
    fila: int
    cuenta: str
    descripcion: str
    fecha: date | None
    debe: float
    haber: float
    moneda: str
    # Columna "Asiento" (sinónimos: partida/asiento/no.): identifica a qué
    # asiento contable pertenece la partida, para el cuadre por asiento de
    # RN-01 (ver validadores.contable.reglas). None si el archivo no trae
    # esa columna o si la celda viene vacía.
    asiento: str | None = None


@dataclass(frozen=True)
class FilaTotal:
    hoja: str
    fila: int
    debe_declarado: float
    haber_declarado: float
    debe_es_formula: bool
    haber_es_formula: bool


@dataclass(frozen=True)
class LibroContable:
    partidas: list[PartidaContable] = field(default_factory=list)
    fila_total: FilaTotal | None = None


def _normalizar(texto: str) -> str:
    """Minúsculas y sin acentos -- "Código"/"codigo" deben comparar igual."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).lower()


def _tokens(valor: object) -> frozenset[str]:
    if valor is None:
        return frozenset()
    return frozenset(_PATRON_TOKEN.findall(_normalizar(str(valor))))


def _a_numero(valor: object) -> float:
    if valor is None:
        return 0.0
    if isinstance(valor, int | float):
        return float(valor)
    return 0.0


def _a_fecha(valor: object) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return None


def _cuenta_a_texto(valor: object) -> str:
    """Los códigos de cuenta deben tratarse como texto incluso si Excel los
    guardó como número (p. ej. "1101" tecleado sin formato de texto se
    vuelve 1101.0) -- preserva "6112.03.00" tal cual (ya es texto, nunca
    podría ser un float válido con dos puntos) y vuelve "1101" un entero
    limpio en vez de "1101.0"."""
    if isinstance(valor, float):
        if valor.is_integer():
            return str(int(valor))
        return f"{valor:.10f}".rstrip("0").rstrip(".")
    return str(valor).strip()


def _fila_es_titulo_combinado(ws: Worksheet, fila: int) -> bool:
    """Una fila ocupada por una sola celda combinada que abarca varias
    columnas es un título/banner (p. ej. el nombre de la empresa en la fila
    1), no un encabezado ni una fila de datos -- se ignora al buscar la
    tabla."""
    for rango in ws.merged_cells.ranges:
        if rango.min_row == fila and rango.max_row == fila and (rango.max_col - rango.min_col) >= 2:
            return True
    return False


@dataclass(frozen=True)
class _Encabezado:
    fila: int
    columnas: dict[str, int]  # rol -> número de columna (1-based)
    moneda_por_defecto: str


def _moneda_desde_encabezados(textos: list[str]) -> str:
    """"(Q)" o "($)" en cualquier celda del encabezado (p. ej. "Debe (Q)")
    fija la moneda de todo el documento cuando no hay una columna "Moneda"
    dedicada. Q por defecto si no se encuentra ninguna marca."""
    for texto in textos:
        normal = texto.lower()
        if "(q)" in normal:
            return "Q"
        if "($)" in normal:
            return "USD"
    return "Q"


def _resolver_columnas(celdas: list[object]) -> dict[str, int]:
    """Asigna cada rol (debe/haber/cuenta/descripcion/fecha/asiento/moneda)
    a lo más una columna, en dos pasadas: primero las señales fuertes/
    inequívocas, después "cuenta" como respaldo débil solo si ninguna
    columna fuerte ya cubrió ese rol."""
    columnas: dict[str, int] = {}
    tokens_por_columna = {indice: _tokens(valor) for indice, valor in enumerate(celdas, start=1)}

    pases_fuertes = (
        ("debe", _SINONIMOS_DEBE),
        ("haber", _SINONIMOS_HABER),
        ("cuenta", _SINONIMOS_CUENTA_FUERTE),
        ("descripcion", _SINONIMOS_DESCRIPCION),
        ("fecha", _SINONIMOS_FECHA),
        ("asiento", _SINONIMOS_ASIENTO),
        ("moneda", _SINONIMOS_MONEDA),
    )
    for rol, sinonimos in pases_fuertes:
        if rol in columnas:
            continue
        for indice, tokens in tokens_por_columna.items():
            if indice in columnas.values():
                continue
            if tokens & sinonimos:
                columnas[rol] = indice
                break

    if "cuenta" not in columnas:
        for indice, tokens in tokens_por_columna.items():
            if indice in columnas.values():
                continue
            if tokens & _SINONIMOS_CUENTA_DEBIL:
                columnas["cuenta"] = indice
                break

    return columnas


def _detectar_encabezado(ws: Worksheet) -> _Encabezado | None:
    """Busca, en las primeras `MAX_FILAS_BUSQUEDA_ENCABEZADO` filas de la
    hoja, la primera fila que tenga al menos columnas Debe, Haber y Cuenta
    reconocibles -- esa combinación es la mínima para poder validar un
    libro contable (RN-01/RN-02); Descripción/Fecha/Asiento/Moneda son
    opcionales. Devuelve None si no se encontró ninguna."""
    ultima_fila = min(ws.max_row, MAX_FILAS_BUSQUEDA_ENCABEZADO)
    for fila in range(1, ultima_fila + 1):
        if _fila_es_titulo_combinado(ws, fila):
            continue
        celdas = [ws.cell(row=fila, column=c).value for c in range(1, ws.max_column + 1)]
        if all(valor is None for valor in celdas):
            continue
        columnas = _resolver_columnas(celdas)
        if {"debe", "haber", "cuenta"} <= columnas.keys():
            textos_encabezado = [str(v) for v in celdas if v is not None]
            moneda_por_defecto = (
                "Q" if "moneda" in columnas else _moneda_desde_encabezados(textos_encabezado)
            )
            return _Encabezado(fila=fila, columnas=columnas, moneda_por_defecto=moneda_por_defecto)
    return None


def _fila_es_de_totales(celdas: list[object]) -> bool:
    """"TOTAL"/"SUMA"/"SUMAS IGUALES" en cualquier columna de la fila (no
    solo en la primera) -- en Libro_Diario_Ejercicio_Contable_con_Errores.
    xlsx, "SUMA TOTAL" aparece en la columna de descripción, no en la A."""
    for valor in celdas:
        if _tokens(valor) & {"total", "totales", "suma", "sumas"}:
            return True
    return False


def _leer_hoja(
    ws_formulas: Worksheet, ws_valores: Worksheet, nombre_hoja: str
) -> LibroContable | None:
    encabezado = _detectar_encabezado(ws_valores)
    if encabezado is None:
        return None

    col = encabezado.columnas
    partidas: list[PartidaContable] = []
    fila_total: FilaTotal | None = None

    for num_fila in range(encabezado.fila + 1, ws_valores.max_row + 1):
        celdas = [
            ws_valores.cell(row=num_fila, column=c).value
            for c in range(1, ws_valores.max_column + 1)
        ]

        if _fila_es_de_totales(celdas):
            celda_debe_f = ws_formulas.cell(row=num_fila, column=col["debe"])
            celda_haber_f = ws_formulas.cell(row=num_fila, column=col["haber"])
            fila_total = FilaTotal(
                hoja=nombre_hoja,
                fila=num_fila,
                debe_declarado=_a_numero(ws_valores.cell(row=num_fila, column=col["debe"]).value),
                haber_declarado=_a_numero(ws_valores.cell(row=num_fila, column=col["haber"]).value),
                debe_es_formula=celda_debe_f.data_type == "f",
                haber_es_formula=celda_haber_f.data_type == "f",
            )
            break

        valor_cuenta = celdas[col["cuenta"] - 1]
        valor_debe = celdas[col["debe"] - 1]
        valor_haber = celdas[col["haber"] - 1]
        if valor_cuenta is None and valor_debe is None and valor_haber is None:
            break  # fila vacía: fin de la tabla (sin fila de totales)

        cuenta = _cuenta_a_texto(valor_cuenta) if valor_cuenta is not None else ""
        if not cuenta:
            continue

        if "moneda" in col:
            valor_moneda = celdas[col["moneda"] - 1]
            moneda = (
                str(valor_moneda).strip().upper() if valor_moneda else encabezado.moneda_por_defecto
            )
        else:
            moneda = encabezado.moneda_por_defecto

        descripcion = str(celdas[col["descripcion"] - 1] or "") if "descripcion" in col else ""
        fecha = _a_fecha(celdas[col["fecha"] - 1]) if "fecha" in col else None
        if "asiento" in col:
            valor_asiento = celdas[col["asiento"] - 1]
            asiento = str(valor_asiento).strip() if valor_asiento not in (None, "") else None
        else:
            asiento = None

        partidas.append(
            PartidaContable(
                hoja=nombre_hoja,
                fila=num_fila,
                cuenta=cuenta,
                descripcion=descripcion,
                fecha=fecha,
                debe=_a_numero(valor_debe),
                haber=_a_numero(valor_haber),
                moneda=moneda,
                asiento=asiento,
            )
        )

    return LibroContable(partidas=partidas, fila_total=fila_total)


def leer_libro_contable(archivo: io.BytesIO | str, hoja: str | None = None) -> LibroContable:
    """Lee un Excel contable detectando la tabla de partidas por encabezado
    (ver `_detectar_encabezado`) en vez de asumir una plantilla fija. Si se
    da `hoja`, solo se busca ahí; si no, se recorren todas las hojas del
    archivo en orden y se usa la primera donde se detecte una tabla.

    Se hacen dos lecturas (con y sin `data_only`) para poder distinguir una
    fórmula de un valor fijo en la fila de totales (RNF-03: el parser no
    calcula nada, solo reporta lo que hay en la hoja -- el cuadre real lo
    recalcula `validadores.contable.reglas` sumando las partidas en Python,
    nunca confiando en el total que declara la propia hoja).
    """
    if hasattr(archivo, "seek"):
        archivo.seek(0)
    wb_formulas = load_workbook(archivo, data_only=False)
    if hasattr(archivo, "seek"):
        archivo.seek(0)
    wb_valores = load_workbook(archivo, data_only=True)

    nombres_hoja = [hoja] if hoja else list(wb_formulas.sheetnames)
    for nombre_hoja in nombres_hoja:
        resultado = _leer_hoja(wb_formulas[nombre_hoja], wb_valores[nombre_hoja], nombre_hoja)
        if resultado is not None:
            return resultado

    raise TablaContableNoDetectadaError(
        "No se encontró una fila de encabezado con columnas Debe/Haber/Cuenta "
        f"reconocibles en ninguna hoja revisada ({', '.join(nombres_hoja)})"
    )
