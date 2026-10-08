"""Pruebas de clasificación de confianza y detección de páginas ilegibles
(CU-06, Bloque 2, RN-06)."""

from ocr.calidad import (
    NIVEL_DUDOSA,
    NIVEL_OK,
    NIVEL_REVISAR,
    Umbrales,
    clasificar_confianza,
    es_pagina_ilegible,
)
from ocr.modelos import Linea, Palabra, ResultadoPagina

UMBRALES = Umbrales(conf_dudosa=60, conf_revisar=80, pagina_ilegible=50)


def _pagina(
    confianza_media: float, *, palabras: tuple[Palabra, ...] = (), texto_nativo: bool = False
) -> ResultadoPagina:
    return ResultadoPagina(
        numero=1,
        ancho_px=100,
        alto_px=100,
        lineas=(),
        palabras=palabras,
        confianza_media=confianza_media,
        texto_nativo=texto_nativo,
    )


# --- clasificar_confianza --------------------------------------------------


def test_clasificar_confianza_por_debajo_de_conf_dudosa_es_dudosa() -> None:
    assert clasificar_confianza(59.9, UMBRALES) == NIVEL_DUDOSA


def test_clasificar_confianza_en_el_borde_de_conf_dudosa_ya_no_es_dudosa() -> None:
    assert clasificar_confianza(60.0, UMBRALES) == NIVEL_REVISAR


def test_clasificar_confianza_entre_umbrales_es_revisar() -> None:
    assert clasificar_confianza(75.0, UMBRALES) == NIVEL_REVISAR


def test_clasificar_confianza_en_el_borde_de_conf_revisar_ya_es_ok() -> None:
    assert clasificar_confianza(80.0, UMBRALES) == NIVEL_OK


def test_clasificar_confianza_alta_es_ok() -> None:
    assert clasificar_confianza(95.0, UMBRALES) == NIVEL_OK


# --- es_pagina_ilegible -----------------------------------------------------


def test_pagina_con_texto_nativo_nunca_es_ilegible() -> None:
    assert es_pagina_ilegible(_pagina(0.0, texto_nativo=True), UMBRALES) is False


def test_pagina_sin_ninguna_palabra_reconocida_es_ilegible() -> None:
    assert es_pagina_ilegible(_pagina(0.0, palabras=()), UMBRALES) is True


def test_pagina_con_confianza_media_baja_es_ilegible() -> None:
    palabra = Palabra(texto="x", izquierda=0, arriba=0, ancho=1, alto=1, confianza=40.0)
    assert es_pagina_ilegible(_pagina(40.0, palabras=(palabra,)), UMBRALES) is True


def test_pagina_con_confianza_media_suficiente_no_es_ilegible() -> None:
    palabra = Palabra(texto="x", izquierda=0, arriba=0, ancho=1, alto=1, confianza=70.0)
    assert es_pagina_ilegible(_pagina(70.0, palabras=(palabra,)), UMBRALES) is False


def test_umbrales_desde_entorno_usa_los_valores_por_defecto_del_rf_11(monkeypatch) -> None:  # noqa: ANN001
    from ocr.calidad import umbrales_desde_entorno

    monkeypatch.delenv("OCR_CONF_DUDOSA", raising=False)
    monkeypatch.delenv("OCR_CONF_REVISAR", raising=False)
    monkeypatch.delenv("OCR_PAGINA_ILEGIBLE", raising=False)

    umbrales = umbrales_desde_entorno()
    assert umbrales == Umbrales(conf_dudosa=60.0, conf_revisar=80.0, pagina_ilegible=50.0)


def test_umbrales_desde_entorno_respeta_variables_configuradas(monkeypatch) -> None:  # noqa: ANN001
    from ocr.calidad import umbrales_desde_entorno

    monkeypatch.setenv("OCR_CONF_DUDOSA", "55")
    monkeypatch.setenv("OCR_CONF_REVISAR", "85")
    monkeypatch.setenv("OCR_PAGINA_ILEGIBLE", "45")

    umbrales = umbrales_desde_entorno()
    assert umbrales == Umbrales(conf_dudosa=55.0, conf_revisar=85.0, pagina_ilegible=45.0)


def test_linea_no_se_usa_en_calidad_pero_el_modelo_la_admite() -> None:
    # Humo: ResultadoPagina con líneas reales no rompe la clasificación.
    linea = Linea(texto="hola", palabras=())
    pagina = ResultadoPagina(
        numero=1, ancho_px=10, alto_px=10, lineas=(linea,), palabras=(), confianza_media=90.0
    )
    assert es_pagina_ilegible(pagina, UMBRALES) is True  # sin palabras -> ilegible
