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


def test_mezcla_de_moneda_sin_tipo_de_cambio_genera_hallazgo_rn05() -> None:
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
    assert rn05[0].moneda == "Q/USD"


def test_ningun_calculo_de_moneda_lo_hace_el_validador_rnf03() -> None:
    """RNF-03: el validador nunca convierte montos entre monedas, solo señala
    la mezcla. No debe existir ninguna operación de conversión en el módulo."""
    import inspect

    import validadores.contable.reglas as modulo

    codigo_fuente = inspect.getsource(modulo)
    for palabra_prohibida in ("tipo_de_cambio", "tasa_cambio", "exchange_rate"):
        assert palabra_prohibida not in codigo_fuente
