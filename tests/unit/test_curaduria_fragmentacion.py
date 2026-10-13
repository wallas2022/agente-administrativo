"""P-15 Bloque 2: fragmentación acotada (tope de tokens, solapamiento y limpieza)."""

import pymupdf
import pytest

from curaduria.extraccion import (
    agrupar_por_seccion,
    estimar_tokens,
    extraer_fragmentos,
)
from parsers.segmentos import SegmentoTexto

MAX = 450
SOLAPE = 60


def _parrafo(indice: int, palabras: int = 60) -> str:
    return f"P{indice} " + " ".join(f"palabra{indice}_{n}" for n in range(palabras)) + "."


def _seg(texto: str, ubicacion: str = "párrafo 1") -> SegmentoTexto:
    return SegmentoTexto(texto=texto, ubicacion=ubicacion)


def test_seccion_corta_queda_en_un_solo_fragmento_sin_cambios() -> None:
    fragmentos = agrupar_por_seccion([_seg("§1 Alcance"), _seg("Uno."), _seg("Dos.")])
    assert [(f.seccion, f.contenido) for f in fragmentos] == [("§1", "Uno.\nDos.")]


def test_seccion_larga_se_divide_y_ningun_fragmento_supera_el_tope() -> None:
    segmentos = [_seg("§2 Larga")] + [_seg(_parrafo(i)) for i in range(40)]
    fragmentos = agrupar_por_seccion(segmentos, max_tokens=MAX, solape_tokens=SOLAPE)

    assert len(fragmentos) > 1
    assert all(f.seccion == "§2" for f in fragmentos)
    assert all(estimar_tokens(f.contenido) <= MAX for f in fragmentos)


def test_hay_solapamiento_entre_fragmentos_consecutivos() -> None:
    segmentos = [_seg("§2 Larga")] + [_seg(_parrafo(i)) for i in range(40)]
    fragmentos = agrupar_por_seccion(segmentos, max_tokens=MAX, solape_tokens=SOLAPE)

    for anterior, siguiente in zip(fragmentos, fragmentos[1:], strict=False):
        ultima_palabra = anterior.contenido.split()[-1]
        assert ultima_palabra in siguiente.contenido.split()[:80]
        assert estimar_tokens(siguiente.contenido) <= MAX


def test_no_se_pierde_contenido_al_dividir() -> None:
    segmentos = [_seg("§2 Larga")] + [_seg(_parrafo(i)) for i in range(40)]
    fragmentos = agrupar_por_seccion(segmentos, max_tokens=MAX, solape_tokens=SOLAPE)
    unido = " ".join(f.contenido for f in fragmentos)
    for i in range(40):
        assert f"palabra{i}_0 " in unido and f"palabra{i}_59." in unido


def test_un_parrafo_gigante_sin_puntos_se_divide_por_palabras() -> None:
    texto = " ".join(f"w{n}" for n in range(6000))
    fragmentos = agrupar_por_seccion([_seg(texto)], max_tokens=MAX, solape_tokens=SOLAPE)
    assert len(fragmentos) > 1
    assert all(estimar_tokens(f.contenido) <= MAX for f in fragmentos)


def test_una_palabra_enorme_sin_espacios_tambien_respeta_el_tope() -> None:
    fragmentos = agrupar_por_seccion([_seg("x" * 10_000)], max_tokens=MAX, solape_tokens=SOLAPE)
    assert all(estimar_tokens(f.contenido) <= MAX for f in fragmentos)


def test_el_tope_es_configurable_por_variable_de_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRAGMENTO_MAX_TOKENS", "100")
    monkeypatch.setenv("FRAGMENTO_SOLAPE_TOKENS", "10")
    fragmentos = agrupar_por_seccion([_seg(_parrafo(0, 200))])
    assert len(fragmentos) > 1
    assert all(estimar_tokens(f.contenido) <= 100 for f in fragmentos)


def test_cambio_de_pagina_en_pdf_abre_fragmento_con_su_pagina_y_conserva_la_seccion() -> None:
    fragmentos = agrupar_por_seccion(
        [
            _seg("§1 Alcance", "Página 1, bloque 0"),
            _seg("Texto de la página uno.", "Página 1, bloque 1"),
            _seg("Texto de la página dos.", "Página 2, bloque 0"),
        ]
    )
    assert [(f.seccion, f.pagina) for f in fragmentos] == [("§1", 1), ("§1", 2)]


def test_limpia_lineas_de_indice_con_puntos_guia() -> None:
    fragmentos = agrupar_por_seccion(
        [
            _seg("§1 Contenido"),
            _seg("1. Introducción ........................ 3"),
            _seg("2. Alcance . . . . . . . . . . . . 5"),
            _seg("Texto real del documento."),
        ]
    )
    assert fragmentos[0].contenido == "Texto real del documento."


def test_limpia_caracteres_de_control() -> None:
    fragmentos = agrupar_por_seccion([_seg("Hola\x00 mun\x07do\x0c.")])
    assert fragmentos[0].contenido == "Hola mundo."


def test_limpia_encabezados_y_pies_repetidos_en_varias_paginas() -> None:
    temas = ["cierre", "conciliación", "arqueo", "depreciación", "provisiones"]
    segmentos = []
    for pagina in range(1, 6):
        segmentos.append(_seg("MANUAL INTERNO - CONFIDENCIAL", f"Página {pagina}, bloque 0"))
        segmentos.append(_seg(f"Regla de {temas[pagina - 1]}.", f"Página {pagina}, bloque 1"))
        segmentos.append(_seg(f"Página {pagina} de 5", f"Página {pagina}, bloque 2"))
    texto = " ".join(f.contenido for f in agrupar_por_seccion(segmentos))
    assert "CONFIDENCIAL" not in texto
    assert "de 5" not in texto
    assert all(f"Regla de {tema}." in texto for tema in temas)


def test_no_borra_texto_repetido_si_es_un_encabezado_de_seccion_o_hay_pocas_paginas() -> None:
    segmentos = [
        _seg("Aviso legal", "Página 1, bloque 0"),
        _seg("A.", "Página 1, bloque 1"),
        _seg("Aviso legal", "Página 2, bloque 0"),
        _seg("B.", "Página 2, bloque 1"),
    ]
    texto = " ".join(f.contenido for f in agrupar_por_seccion(segmentos))
    assert texto.count("Aviso legal") == 2


def test_pdf_de_300_paginas_no_genera_fragmentos_sobre_el_tope() -> None:
    documento = pymupdf.open()
    parrafo = " ".join(f"término{n}" for n in range(900))
    for _ in range(300):
        pagina = documento.new_page()
        pagina.insert_textbox(pymupdf.Rect(30, 30, 565, 810), parrafo, fontsize=7)
    contenido = documento.tobytes()
    documento.close()

    fragmentos = extraer_fragmentos("pdf", contenido)

    assert len(fragmentos) >= 300
    assert max(estimar_tokens(f.contenido) for f in fragmentos) <= 450
