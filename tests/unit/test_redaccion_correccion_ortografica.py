from ortografia.cliente_languagetool import CoincidenciaLT
from validadores.redaccion.correccion_ortografica import corregir_ortografia_parrafo


def _coincidencia(
    texto: str, offset: int, *, sugerencias: list[str], categoria: str = "TYPOS"
) -> CoincidenciaLT:
    return CoincidenciaLT(
        texto=texto,
        offset=offset,
        longitud=len(texto),
        mensaje="mensaje de prueba",
        sugerencias=sugerencias,
        regla_id="REGLA_X",
        categoria=categoria,
    )


def test_corrige_un_error_tipografico_claro() -> None:
    texto = "el dia de hoy se aprobo el gasto"
    coincidencias = [
        _coincidencia("dia", 3, sugerencias=["día"]),
        _coincidencia("aprobo", 17, sugerencias=["aprobó"]),
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
