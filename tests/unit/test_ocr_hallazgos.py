"""Pruebas de detección de "palabra dudosa" de CU-06 (Bloque 2, RN-06):
clasificación por confianza + sugerencias opcionales de LanguageTool, nunca
autocorrige, excluye tokens con dígitos y términos del glosario."""

from ocr.calidad import Umbrales
from ocr.hallazgos import detectar_palabras_dudosas
from ocr.modelos import Linea, Palabra, ResultadoPagina
from ortografia.cliente_languagetool import CoincidenciaLT

UMBRALES = Umbrales(conf_dudosa=60, conf_revisar=80, pagina_ilegible=50)


def _palabra(texto: str, confianza: float) -> Palabra:
    return Palabra(texto=texto, izquierda=0, arriba=0, ancho=10, alto=10, confianza=confianza)


def _pagina_con_una_linea(
    palabras: list[Palabra], *, numero: int = 1, texto_nativo: bool = False
) -> ResultadoPagina:
    linea = Linea(texto=" ".join(p.texto for p in palabras), palabras=tuple(palabras))
    confianza_media = sum(p.confianza for p in palabras) / len(palabras) if palabras else 0.0
    return ResultadoPagina(
        numero=numero,
        ancho_px=100,
        alto_px=100,
        lineas=(linea,),
        palabras=tuple(palabras),
        confianza_media=confianza_media,
        texto_nativo=texto_nativo,
    )


def test_palabra_con_confianza_alta_no_es_dudosa() -> None:
    pagina = _pagina_con_una_linea([_palabra("Hola", 95.0)])
    assert detectar_palabras_dudosas([pagina], umbrales=UMBRALES) == []


def test_palabra_con_confianza_baja_es_dudosa_con_su_nivel() -> None:
    pagina = _pagina_con_una_linea([_palabra("Mllndo", 55.0)])
    dudosas = detectar_palabras_dudosas([pagina], umbrales=UMBRALES)
    assert len(dudosas) == 1
    assert dudosas[0].texto == "Mllndo"
    assert dudosas[0].nivel == "dudosa"
    assert dudosas[0].pagina == 1
    assert dudosas[0].linea == "Mllndo"


def test_palabra_en_rango_amarillo_se_marca_revisar() -> None:
    pagina = _pagina_con_una_linea([_palabra("Alg0", 70.0)])
    dudosas = detectar_palabras_dudosas([pagina], umbrales=UMBRALES)
    assert dudosas[0].nivel == "revisar"


def test_pagina_con_texto_nativo_no_genera_palabras_dudosas() -> None:
    pagina = _pagina_con_una_linea([_palabra("loquesea", 10.0)], texto_nativo=True)
    assert detectar_palabras_dudosas([pagina], umbrales=UMBRALES) == []


def test_pagina_ilegible_no_genera_palabras_dudosas_sueltas() -> None:
    pagina = _pagina_con_una_linea([_palabra("x", 20.0)])  # confianza media 20 < 50 ilegible
    assert detectar_palabras_dudosas([pagina], umbrales=UMBRALES) == []


def test_sugerencia_de_languagetool_se_asocia_a_la_palabra_dudosa() -> None:
    pagina = _pagina_con_una_linea([_palabra("Hola", 95.0), _palabra("mllndo", 50.0)])

    def _lt_falso(texto: str) -> list[CoincidenciaLT]:
        inicio = texto.index("mllndo")
        return [
            CoincidenciaLT(
                texto="mllndo",
                offset=inicio,
                longitud=len("mllndo"),
                mensaje="Posible error ortográfico",
                sugerencias=["mundo"],
                regla_id="MORFOLOGIK_RULE_ES",
                categoria="TYPOS",
            )
        ]

    dudosas = detectar_palabras_dudosas([pagina], umbrales=UMBRALES, funcion_revisar_lt=_lt_falso)
    assert len(dudosas) == 1
    assert dudosas[0].texto == "mllndo"
    assert dudosas[0].sugerencia == "mundo"


def test_sugerencia_con_digito_se_descarta_aunque_la_palabra_sea_dudosa() -> None:
    # Dos palabras: una confiable (mantiene la media de la página por
    # encima de OCR_PAGINA_ILEGIBLE) y la dudosa con dígitos a probar.
    pagina = _pagina_con_una_linea([_palabra("Total", 95.0), _palabra("Q1,25O.OO", 40.0)])

    def _lt_falso(texto: str) -> list[CoincidenciaLT]:
        inicio = texto.index("Q1,25O.OO")
        return [
            CoincidenciaLT(
                texto="Q1,25O.OO",
                offset=inicio,
                longitud=len("Q1,25O.OO"),
                mensaje="posible error",
                sugerencias=["Q1,250.00"],
                regla_id="X",
                categoria="TYPOS",
            )
        ]

    dudosas = detectar_palabras_dudosas([pagina], umbrales=UMBRALES, funcion_revisar_lt=_lt_falso)
    assert len(dudosas) == 1
    assert dudosas[0].sugerencia is None  # RN-06: nunca se sugiere nada para tokens con dígitos


def test_sugerencia_para_termino_de_glosario_se_descarta() -> None:
    pagina = _pagina_con_una_linea([_palabra("SFC", 55.0)])

    def _lt_falso(texto: str) -> list[CoincidenciaLT]:
        return [
            CoincidenciaLT(
                texto="SFC",
                offset=0,
                longitud=3,
                mensaje="palabra desconocida",
                sugerencias=["SAC"],
                regla_id="MORFOLOGIK_RULE_ES",
                categoria="TYPOS",
            )
        ]

    dudosas = detectar_palabras_dudosas(
        [pagina], umbrales=UMBRALES, glosario={"SFC"}, funcion_revisar_lt=_lt_falso
    )
    assert len(dudosas) == 1
    assert dudosas[0].sugerencia is None


def test_nunca_autocorrige_el_texto_de_la_palabra() -> None:
    """La palabra dudosa conserva el texto EXACTO reconocido por Tesseract,
    aunque haya una sugerencia disponible -- la sugerencia es solo dato
    auxiliar, nunca reemplaza `texto`."""
    pagina = _pagina_con_una_linea([_palabra("mllndo", 50.0)])

    def _lt_falso(texto: str) -> list[CoincidenciaLT]:
        return [
            CoincidenciaLT(
                texto="mllndo",
                offset=0,
                longitud=6,
                mensaje="x",
                sugerencias=["mundo"],
                regla_id="MORFOLOGIK_RULE_ES",
                categoria="TYPOS",
            )
        ]

    dudosas = detectar_palabras_dudosas([pagina], umbrales=UMBRALES, funcion_revisar_lt=_lt_falso)
    assert dudosas[0].texto == "mllndo"
    assert dudosas[0].sugerencia == "mundo"
