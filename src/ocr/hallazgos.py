"""Detección de "palabra dudosa" de CU-06 (Bloque 2, RN-06): cada palabra
reconocida por debajo de `OCR_CONF_REVISAR` se reporta con su página, línea,
texto, confianza y nivel -- para reutilizar la vista de hallazgos ya
existente (CU-05/CU-02).

Enriquecimiento opcional con LanguageTool (`funcion_revisar_lt`), SOLO como
sugerencia (nunca se autocorrige el texto reconocido): se corre sobre el
texto de la línea completa (da contexto a LanguageTool) y cada coincidencia
se asocia a la(s) palabra(s) que solapa por offset. Se descartan sugerencias
para términos del glosario y para cualquier token con un dígito (monto,
fecha o código) -- RN-06.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ocr.calidad import NIVEL_OK, Umbrales, clasificar_confianza, es_pagina_ilegible
from ocr.modelos import Linea, ResultadoPagina
from ortografia.cliente_languagetool import CoincidenciaLT

FuncionRevisarLT = Callable[[str], list[CoincidenciaLT]]


@dataclass(frozen=True)
class PalabraDudosa:
    pagina: int
    linea: str
    texto: str
    confianza: float
    nivel: str
    sugerencia: str | None = None


def _contiene_digito(texto: str) -> bool:
    return any(caracter.isdigit() for caracter in texto)


def _es_termino_de_glosario(texto: str, glosario_normalizado: set[str]) -> bool:
    return texto.strip().lower() in glosario_normalizado


def _offsets_en_linea(linea: Linea) -> list[tuple[int, int]]:
    offsets = []
    cursor = 0
    for palabra in linea.palabras:
        offsets.append((cursor, cursor + len(palabra.texto)))
        cursor += len(palabra.texto) + 1  # +1 por el espacio que las une
    return offsets


def _sugerencias_lt_por_palabra(
    linea: Linea, *, glosario_normalizado: set[str], funcion_revisar_lt: FuncionRevisarLT
) -> dict[int, str]:
    coincidencias = funcion_revisar_lt(linea.texto)
    offsets = _offsets_en_linea(linea)
    sugerencias: dict[int, str] = {}
    for coincidencia in coincidencias:
        if not coincidencia.sugerencias:
            continue
        if _contiene_digito(coincidencia.texto):
            continue
        if _es_termino_de_glosario(coincidencia.texto, glosario_normalizado):
            continue
        inicio_c = coincidencia.offset
        fin_c = coincidencia.offset + coincidencia.longitud
        for indice, (inicio_p, fin_p) in enumerate(offsets):
            if indice in sugerencias:
                continue
            if inicio_c < fin_p and fin_c > inicio_p:
                sugerencias[indice] = coincidencia.sugerencias[0]
    return sugerencias


def detectar_palabras_dudosas(
    paginas: list[ResultadoPagina],
    *,
    umbrales: Umbrales,
    glosario: set[str] | None = None,
    funcion_revisar_lt: FuncionRevisarLT | None = None,
) -> list[PalabraDudosa]:
    """Una página ilegible (Bloque 2: cero texto, PP-06) no aporta palabras
    dudosas -- ya está marcada como ilegible en su conjunto; una página con
    texto nativo de PDF tampoco (es texto real, no un reconocimiento con
    incertidumbre que reportar)."""
    glosario_normalizado = {t.strip().lower() for t in (glosario or set())}
    dudosas: list[PalabraDudosa] = []

    for pagina in paginas:
        if pagina.texto_nativo or es_pagina_ilegible(pagina, umbrales):
            continue
        for linea in pagina.lineas:
            sugerencias_por_indice: dict[int, str] = {}
            if funcion_revisar_lt is not None:
                sugerencias_por_indice = _sugerencias_lt_por_palabra(
                    linea,
                    glosario_normalizado=glosario_normalizado,
                    funcion_revisar_lt=funcion_revisar_lt,
                )
            for indice, palabra in enumerate(linea.palabras):
                nivel = clasificar_confianza(palabra.confianza, umbrales)
                if nivel == NIVEL_OK:
                    continue
                dudosas.append(
                    PalabraDudosa(
                        pagina=pagina.numero,
                        linea=linea.texto,
                        texto=palabra.texto,
                        confianza=palabra.confianza,
                        nivel=nivel,
                        sugerencia=sugerencias_por_indice.get(indice),
                    )
                )
    return dudosas
