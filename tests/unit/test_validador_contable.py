from datetime import date

from parsers.excel import FilaTotal, LibroContable, PartidaContable
from validadores.contable.reglas import validar_libro_contable

CATALOGO = {"1010", "4010", "2010", "5010"}
PERIODO = (2026, 1)


def _partida(**kwargs) -> PartidaContable:
    base = dict(
        hoja="Partidas",
        fila=2,
        cuenta="1010",
        descripcion="Cobro",
        fecha=date(2026, 1, 5),
        debe=100.0,
        haber=0.0,
        moneda="Q",
    )
    base.update(kwargs)
    return PartidaContable(**base)


def test_libro_cuadrado_sin_hallazgos_de_cuadre() -> None:
    libro = LibroContable(
        partidas=[
            _partida(fila=2, cuenta="1010", debe=100.0, haber=0.0),
            _partida(fila=3, cuenta="4010", debe=0.0, haber=100.0),
        ]
    )

    hallazgos = validar_libro_contable(libro, catalogo=CATALOGO, periodo=PERIODO)

    codigos = [h.regla_codigo for h in hallazgos]
    assert "RN-01" not in codigos


def test_descuadre_genera_hallazgo_rn01_con_monto_y_severidad_alta() -> None:
    libro = LibroContable(
        partidas=[
            _partida(fila=2, cuenta="1010", debe=100.0, haber=0.0),
            _partida(fila=3, cuenta="4010", debe=0.0, haber=90.0),
        ]
    )

    hallazgos = validar_libro_contable(libro, catalogo=CATALOGO, periodo=PERIODO)
    rn01 = [h for h in hallazgos if h.regla_codigo == "RN-01"]

    assert len(rn01) == 1
    assert rn01[0].severidad == "alta"
    assert rn01[0].monto == 10.0


def test_cuenta_inexistente_genera_hallazgo_rn02() -> None:
    libro = LibroContable(partidas=[_partida(fila=2, cuenta="9999")])

    hallazgos = validar_libro_contable(libro, catalogo=CATALOGO, periodo=PERIODO)
    rn02 = [h for h in hallazgos if h.regla_codigo == "RN-02"]

    assert len(rn02) == 1
    assert rn02[0].ubicacion == "Partidas!A2"
    assert rn02[0].severidad == "alta"


def test_formula_de_total_reemplazada_por_valor_genera_hallazgo() -> None:
    libro = LibroContable(
        partidas=[_partida(fila=2, cuenta="1010", debe=100.0, haber=0.0)],
        fila_total=FilaTotal(
            hoja="Partidas",
            fila=3,
            debe_declarado=100.0,
            haber_declarado=100.0,
            debe_es_formula=False,
            haber_es_formula=True,
        ),
    )

    hallazgos = validar_libro_contable(libro, catalogo=CATALOGO, periodo=PERIODO)
    formula = [h for h in hallazgos if h.regla_codigo == "RN-FORMULA"]

    assert len(formula) == 1
    assert "Debe" in formula[0].descripcion


def test_fecha_fuera_de_periodo_genera_hallazgo_rn03() -> None:
    libro = LibroContable(partidas=[_partida(fila=2, fecha=date(2025, 12, 20))])

    hallazgos = validar_libro_contable(libro, catalogo=CATALOGO, periodo=PERIODO)
    rn03 = [h for h in hallazgos if h.regla_codigo == "RN-03"]

    assert len(rn03) == 1
    assert rn03[0].severidad == "media"


def test_partidas_duplicadas_generan_hallazgo_rn04_por_cada_una() -> None:
    libro = LibroContable(
        partidas=[
            _partida(fila=2, cuenta="1010", debe=100.0, fecha=date(2026, 1, 5)),
            _partida(fila=3, cuenta="1010", debe=100.0, fecha=date(2026, 1, 5)),
        ]
    )

    hallazgos = validar_libro_contable(libro, catalogo=CATALOGO, periodo=PERIODO)
    rn04 = [h for h in hallazgos if h.regla_codigo == "RN-04"]

    assert len(rn04) == 2
    assert {h.ubicacion for h in rn04} == {"Partidas!A2", "Partidas!A3"}


def test_mezcla_de_moneda_reporta_solo_la_partida_que_difiere_de_la_principal() -> None:
    """Con empate 1-1, la principal es la primera en aparecer (Q); solo la
    partida en USD -- la que realmente difiere -- genera un hallazgo."""
    libro = LibroContable(
        partidas=[
            _partida(fila=2, cuenta="1010", moneda="Q"),
            _partida(fila=3, cuenta="1010", moneda="USD"),
        ]
    )

    hallazgos = validar_libro_contable(libro, catalogo=CATALOGO, periodo=PERIODO)
    rn05 = [h for h in hallazgos if h.regla_codigo == "RN-05"]

    assert len(rn05) == 1
    assert rn05[0].severidad == "alta"
    assert rn05[0].ubicacion == "Partidas!A3"
    assert rn05[0].moneda == "USD"


def test_mezcla_de_moneda_reporta_cada_partida_de_la_moneda_minoritaria() -> None:
    libro = LibroContable(
        partidas=[
            _partida(fila=2, cuenta="1010", moneda="Q"),
            _partida(fila=3, cuenta="1010", moneda="Q"),
            _partida(fila=4, cuenta="1010", moneda="USD"),
            _partida(fila=5, cuenta="1010", moneda="USD"),
        ]
    )

    hallazgos = validar_libro_contable(libro, catalogo=CATALOGO, periodo=PERIODO)
    rn05 = [h for h in hallazgos if h.regla_codigo == "RN-05"]

    assert {h.ubicacion for h in rn05} == {"Partidas!A4", "Partidas!A5"}
    assert all(h.moneda == "USD" for h in rn05)


def test_sin_mezcla_de_moneda_no_genera_hallazgo_rn05() -> None:
    libro = LibroContable(
        partidas=[
            _partida(fila=2, cuenta="1010", moneda="Q"),
            _partida(fila=3, cuenta="1010", moneda="Q"),
        ]
    )

    hallazgos = validar_libro_contable(libro, catalogo=CATALOGO, periodo=PERIODO)
    assert not [h for h in hallazgos if h.regla_codigo == "RN-05"]


def test_descuadre_por_asiento_genera_hallazgo_solo_para_el_asiento_afectado() -> None:
    """Dos asientos con la columna Asiento: uno cuadrado (0001) y otro no
    (0002) -- solo el segundo genera hallazgos, uno por cada una de sus
    partidas."""
    libro = LibroContable(
        partidas=[
            _partida(fila=2, cuenta="1010", debe=100.0, haber=0.0, asiento="0001"),
            _partida(fila=3, cuenta="4010", debe=0.0, haber=100.0, asiento="0001"),
            _partida(fila=4, cuenta="1010", debe=50.0, haber=0.0, asiento="0002"),
        ]
    )

    hallazgos = validar_libro_contable(libro, catalogo=CATALOGO, periodo=PERIODO)
    rn01_por_asiento = [
        h for h in hallazgos if h.regla_codigo == "RN-01" and "asiento 0002" in h.descripcion
    ]

    assert {h.ubicacion for h in rn01_por_asiento} == {"Partidas!A4"}
    assert not any("asiento 0001" in h.descripcion for h in hallazgos)


def test_descuadre_por_asiento_no_afecta_partidas_sin_columna_asiento() -> None:
    """Sin la columna Asiento (asiento=None, el default), el documento
    completo puede seguir descuadrado a nivel global sin que el cuadre por
    asiento agregue hallazgos -- evita falsos positivos en archivos con el
    formato previo (sin esa columna)."""
    libro = LibroContable(
        partidas=[
            _partida(fila=2, cuenta="1010", debe=100.0, haber=0.0),
            _partida(fila=3, cuenta="4010", debe=0.0, haber=90.0),
        ]
    )

    hallazgos = validar_libro_contable(libro, catalogo=CATALOGO, periodo=PERIODO)
    rn01 = [h for h in hallazgos if h.regla_codigo == "RN-01"]

    # Solo el descuadre global (_validar_cuadre); nada del cuadre por asiento.
    assert len(rn01) == 1
    assert "Descuadre:" in rn01[0].descripcion


def test_ningun_calculo_de_moneda_lo_hace_el_validador_rnf03() -> None:
    """RNF-03: el validador nunca convierte montos entre monedas, solo señala
    la mezcla. No debe existir ninguna operación de conversión en el módulo."""
    import inspect

    import validadores.contable.reglas as modulo

    codigo_fuente = inspect.getsource(modulo)
    for palabra_prohibida in ("tipo_de_cambio", "tasa_cambio", "exchange_rate"):
        assert palabra_prohibida not in codigo_fuente
