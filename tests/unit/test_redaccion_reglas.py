from parsers.segmentos import SegmentoTexto
from validadores.redaccion.reglas import validar_redaccion


def _segmento(texto: str, ubicacion: str = "Párrafo 1") -> SegmentoTexto:
    return SegmentoTexto(texto=texto, ubicacion=ubicacion)


# --- RD-01: secciones de un Procedimiento -----------------------------------


def test_rd01_detecta_secciones_faltantes_en_un_procedimiento() -> None:
    segmentos = [_segmento("Objetivo: cerrar el mes."), _segmento("Alcance: toda el área.")]
    hallazgos = validar_redaccion(segmentos, tipo_documento="Procedimiento")

    rd01 = [h for h in hallazgos if h.regla_codigo == "RD-01"]
    assert len(rd01) == 1
    assert "responsables" in rd01[0].descripcion
    assert "actividades" in rd01[0].descripcion
    assert "objetivo" not in rd01[0].descripcion
    assert rd01[0].cita_est001 == "§2"


def test_rd01_no_aplica_a_un_correo() -> None:
    segmentos = [_segmento("Hola, les escribo para confirmar la reunión.")]
    hallazgos = validar_redaccion(segmentos, tipo_documento="Correo")

    assert not any(h.regla_codigo == "RD-01" for h in hallazgos)


def test_rd01_no_marca_nada_si_estan_las_seis_secciones() -> None:
    segmentos = [
        _segmento(s)
        for s in [
            "Objetivo: cerrar el mes.",
            "Alcance: toda el área.",
            "Responsables: Jefatura de Contabilidad.",
            "Actividades: 1. Conciliar. 2. Revisar.",
            "Registros: bitácora de cierre.",
            "Control de versiones: v1.0, 2026-01-01.",
        ]
    ]
    hallazgos = validar_redaccion(segmentos, tipo_documento="Procedimiento")

    assert not any(h.regla_codigo == "RD-01" for h in hallazgos)


# --- RD-02: formato de montos -------------------------------------------------


def test_rd02_detecta_monto_mal_formateado() -> None:
    segmentos = [_segmento("El gasto fue de Q1250 durante el mes.")]
    hallazgos = validar_redaccion(segmentos, tipo_documento="Memo")

    rd02 = [h for h in hallazgos if h.regla_codigo == "RD-02"]
    assert len(rd02) == 1
    assert "Q1250" in rd02[0].descripcion


def test_rd02_no_marca_un_monto_bien_formateado() -> None:
    segmentos = [_segmento("El gasto fue de Q 1,250.00 durante el mes.")]
    hallazgos = validar_redaccion(segmentos, tipo_documento="Memo")

    assert not any(h.regla_codigo == "RD-02" for h in hallazgos)


# --- RD-03: formato de fechas --------------------------------------------------


def test_rd03_detecta_fecha_mal_formateada_en_texto_corrido() -> None:
    segmentos = [_segmento("La reunión fue el 28/09/2026 por la tarde.")]
    hallazgos = validar_redaccion(segmentos, tipo_documento="Memo")

    rd03 = [h for h in hallazgos if h.regla_codigo == "RD-03"]
    assert len(rd03) == 1


def test_rd03_no_marca_fecha_textual_correcta_fuera_de_tabla() -> None:
    segmentos = [_segmento("La reunión fue el 28 de septiembre de 2026 por la tarde.")]
    hallazgos = validar_redaccion(segmentos, tipo_documento="Memo")

    assert not any(h.regla_codigo == "RD-03" for h in hallazgos)


def test_rd03_en_tabla_exige_formato_numerico() -> None:
    segmentos = [_segmento("28 de septiembre de 2026", ubicacion="Tabla 1, fila 2, columna 1")]
    hallazgos = validar_redaccion(segmentos, tipo_documento="Memo")

    rd03 = [h for h in hallazgos if h.regla_codigo == "RD-03"]
    assert len(rd03) == 1


def test_rd03_no_marca_fecha_numerica_correcta_en_tabla() -> None:
    segmentos = [_segmento("28/09/2026", ubicacion="Tabla 1, fila 2, columna 1")]
    hallazgos = validar_redaccion(segmentos, tipo_documento="Memo")

    assert not any(h.regla_codigo == "RD-03" for h in hallazgos)


# --- RD-04: siglas no definidas ------------------------------------------------


def test_rd04_detecta_sigla_no_definida_en_su_primer_uso() -> None:
    segmentos = [_segmento("Hay que reportar a la SAT antes de fin de mes.")]
    hallazgos = validar_redaccion(segmentos, tipo_documento="Memo")

    rd04 = [h for h in hallazgos if h.regla_codigo == "RD-04"]
    assert len(rd04) == 1
    assert "SAT" in rd04[0].descripcion


def test_rd04_no_marca_sigla_definida_entre_parentesis() -> None:
    segmentos = [
        _segmento("Hay que reportar a la Superintendencia de Administración Tributaria (SAT).")
    ]
    hallazgos = validar_redaccion(segmentos, tipo_documento="Memo")

    assert not any(h.regla_codigo == "RD-04" for h in hallazgos)


def test_rd04_solo_marca_el_primer_uso_de_cada_sigla() -> None:
    segmentos = [
        _segmento("Hay que reportar a la SAT.", ubicacion="Párrafo 1"),
        _segmento("La SAT también exige el libro de compras.", ubicacion="Párrafo 2"),
    ]
    hallazgos = validar_redaccion(segmentos, tipo_documento="Memo")

    rd04 = [h for h in hallazgos if h.regla_codigo == "RD-04"]
    assert len(rd04) == 1
    assert rd04[0].ubicacion == "Párrafo 1"
