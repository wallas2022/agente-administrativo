from ortografia.cliente_languagetool import CoincidenciaLT
from validadores.redaccion.correccion_ortografica import corregir_ortografia_parrafo


def _coincidencia(
    texto: str,
    offset: int,
    *,
    sugerencias: list[str],
    categoria: str = "TYPOS",
    regla_id: str = "ES_SIMPLE_REPLACE_SIMPLE_X",
) -> CoincidenciaLT:
    return CoincidenciaLT(
        texto=texto,
        offset=offset,
        longitud=len(texto),
        mensaje="mensaje de prueba",
        sugerencias=sugerencias,
        regla_id=regla_id,
        categoria=categoria,
    )


def test_corrige_un_error_tipografico_claro() -> None:
    texto = "el dia de hoy se aprobo el gasto"
    coincidencias = [
        _coincidencia("dia", 3, sugerencias=["día"], regla_id="ES_SIMPLE_REPLACE_SIMPLE_DIA"),
        _coincidencia(
            "aprobo", 17, sugerencias=["aprobó"], regla_id="ES_SIMPLE_REPLACE_SIMPLE_APROBO"
        ),
    ]

    resultado = corregir_ortografia_parrafo(
        texto, glosario=set(), funcion_revisar_lt=lambda _t: coincidencias
    )

    assert resultado == "el día de hoy se aprobó el gasto"


def test_no_corrige_una_categoria_distinta_de_typos() -> None:
    texto = "Hay que reportar a la SAT"
    coincidencias = [_coincidencia("SAT", 22, sugerencias=["SAT definida"], categoria="GRAMMAR")]

    resultado = corregir_ortografia_parrafo(
        texto, glosario=set(), funcion_revisar_lt=lambda _t: coincidencias
    )

    assert resultado == texto


def test_no_corrige_un_termino_del_glosario() -> None:
    texto = "El IVA se calcula sobre el subtotal"
    coincidencias = [_coincidencia("IVA", 3, sugerencias=["iba"])]

    resultado = corregir_ortografia_parrafo(
        texto, glosario={"IVA"}, funcion_revisar_lt=lambda _t: coincidencias
    )

    assert resultado == texto


def test_no_corrige_una_coincidencia_sin_sugerencias() -> None:
    texto = "palabra rara aqui"
    coincidencias = [_coincidencia("rara", 8, sugerencias=[])]

    resultado = corregir_ortografia_parrafo(
        texto, glosario=set(), funcion_revisar_lt=lambda _t: coincidencias
    )

    assert resultado == texto


def test_no_aplica_una_coincidencia_de_multiples_palabras_aunque_sea_typos() -> None:
    """Caso real encontrado probando con LanguageTool real: para "se aprobo"
    (MORFOLOGIK_RULE_ES, categoría TYPOS), la primera sugerencia es "sea
    probo" -- aplicarla a ciegas corrompe la oración en vez de corregirla.
    Un tramo de más de una palabra nunca se autocorrige, sin importar la
    regla."""
    texto = "el dia de hoy se aprobo el gasto"
    coincidencias = [
        _coincidencia(
            "se aprobo",
            14,
            sugerencias=["sea probo", "se aprobó"],
            regla_id="MORFOLOGIK_RULE_ES",
        ),
    ]

    resultado = corregir_ortografia_parrafo(
        texto, glosario=set(), funcion_revisar_lt=lambda _t: coincidencias
    )

    assert resultado == texto


def test_no_aplica_una_regla_morfologik_sobre_una_sigla_no_reconocida() -> None:
    """Otro caso real: LanguageTool marca "DAF" (sigla no reconocida) como
    TYPOS/MORFOLOGIK_RULE_ES y propone "DA" como primera sugerencia -- le
    corta una letra a la sigla en vez de dejarla intacta."""
    texto = "fue aprobado por la DAF."
    coincidencias = [
        _coincidencia("DAF", 21, sugerencias=["DA", "DAR"], regla_id="MORFOLOGIK_RULE_ES"),
    ]

    resultado = corregir_ortografia_parrafo(
        texto, glosario=set(), funcion_revisar_lt=lambda _t: coincidencias
    )

    assert resultado == texto
