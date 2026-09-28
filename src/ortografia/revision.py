"""Motor de revisión ortográfica (RF-10, RF-17, RN-06, CU-05, Bloque O2).

RNF-03 (aplicado por analogía a este caso de uso): LanguageTool es el
detector determinista -- decide qué está mal escrito y con qué severidad.
El LLM nunca escribe ni marca por su cuenta; solo se le consulta, en una
única llamada por lote (igual que `validadores.contable.explicacion`), para
confirmar o descartar los casos AMBIGUOS que ya marcó LanguageTool (p. ej.
"de" vs "dé", "a" vs "ha") -- nunca recibe el documento completo ni texto
que LanguageTool no haya marcado.

Clasificación determinista vs. dudoso (verificado contra LanguageTool 6.5
"es" real, con las frases del dataset de tests/dataset/cu-05/ -- ver
docs/04-pruebas/resultados/local-S2.md):
- Categoría "TYPOS" (MORFOLOGIK_RULE_ES, ES_SIMPLE_REPLACE_*): la palabra
  simplemente no existe en el diccionario -- alta confianza, no pasa por LLM.
- Cualquier otra categoría (p. ej. "DIACRITICS": de/dé, se/sé, además;
  "MISSPELLING" de grammar.xml: a/ha) depende del contexto gramatical de la
  oración -- se manda a validar con el LLM antes de convertirse en hallazgo.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass

from ortografia.cliente_languagetool import CoincidenciaLT
from parsers.segmentos import SegmentoTexto

VERSION_PROMPT_LOTE = "revision-ortografica-lote.v1"

FuncionRevisarLT = Callable[[str], list[CoincidenciaLT]]
FuncionLLM = Callable[[str], str]

CATEGORIAS_DETERMINISTAS = frozenset({"TYPOS"})

_PATRON_SOLO_NUMERO_O_CODIGO = re.compile(r"^[\d.,\s]+$")


@dataclass(frozen=True)
class HallazgoOrtografico:
    severidad: str
    ubicacion: str
    descripcion: str
    correccion_sugerida: str
    texto_original: str
    regla_codigo: str = "RN-06"


def _es_termino_de_glosario(texto: str, glosario_normalizado: set[str]) -> bool:
    return texto.strip().lower() in glosario_normalizado


def _es_numero_o_codigo(texto: str) -> bool:
    return bool(_PATRON_SOLO_NUMERO_O_CODIGO.match(texto.strip()))


def _hallazgo_determinista(
    segmento: SegmentoTexto, coincidencia: CoincidenciaLT
) -> HallazgoOrtografico:
    sugerencia = coincidencia.sugerencias[0] if coincidencia.sugerencias else coincidencia.texto
    return HallazgoOrtografico(
        severidad="media",
        ubicacion=segmento.ubicacion,
        descripcion=f"«{coincidencia.texto}»: {coincidencia.mensaje}",
        correccion_sugerida=sugerencia,
        texto_original=coincidencia.texto,
    )


def _construir_prompt_lote(candidatos: list[tuple[SegmentoTexto, CoincidenciaLT]]) -> str:
    bloques = []
    for indice, (segmento, coincidencia) in enumerate(candidatos):
        sugerencias = ", ".join(f'"{s}"' for s in coincidencia.sugerencias[:3]) or "(ninguna)"
        bloques.append(
            f"### Caso {indice}\n"
            f"- Contexto: {segmento.texto}\n"
            f'- Fragmento marcado: "{coincidencia.texto}"\n'
            f"- Regla que lo marcó: {coincidencia.regla_id} ({coincidencia.mensaje})\n"
            f"- Sugerencia(s) de LanguageTool: {sugerencias}"
        )
    return (
        "Eres un asistente que revisa ortografía y gramática en español (es-GT).\n"
        "LanguageTool marcó los siguientes casos como POSIBLES errores, pero son "
        "ambiguos porque dependen del contexto gramatical de cada oración (p. ej. "
        "\"de\" vs \"dé\", \"a\" vs \"ha\"). Para CADA caso, decide si el fragmento "
        "marcado es realmente un error EN ESE CONTEXTO, o si ya está correcto ahí "
        "(falso positivo de LanguageTool).\n\n"
        "IMPORTANTE: no evalúes ni corrijas nada fuera de los casos listados; no "
        "inventes texto nuevo. Si es un error real, la sugerencia debe ser una de "
        "las de LanguageTool si es correcta, o una corrección mínima equivalente.\n\n"
        "Responde ÚNICAMENTE con un arreglo JSON válido (sin texto antes ni después, "
        "sin bloque de código), con exactamente este formato:\n"
        '[{"indice": 0, "es_error": true, "sugerencia": "...", "explicacion": "..."}, ...]\n\n'
        + "\n\n".join(bloques)
    )


def _parsear_json_lote(texto_crudo: str) -> dict[int, dict[str, object]]:
    """Tolera que el modelo envuelva el JSON en texto o en un bloque de
    código ```json ... ``` -- igual que en `explicacion.py`."""
    candidato = texto_crudo.strip()
    coincidencia = re.search(r"\[.*\]", candidato, re.DOTALL)
    if coincidencia:
        candidato = coincidencia.group(0)
    try:
        datos = json.loads(candidato)
    except json.JSONDecodeError:
        return {}
    if not isinstance(datos, list):
        return {}

    resultado: dict[int, dict[str, object]] = {}
    for entrada in datos:
        if not isinstance(entrada, dict) or "indice" not in entrada:
            continue
        try:
            indice = int(entrada["indice"])
        except (TypeError, ValueError):
            continue
        resultado[indice] = entrada
    return resultado


def _validar_dudosos_con_llm(
    candidatos: list[tuple[SegmentoTexto, CoincidenciaLT]],
    *,
    funcion_llm: FuncionLLM,
) -> list[HallazgoOrtografico]:
    """Una sola llamada al LLM para todos los casos dudosos -- si el LLM no
    responde JSON válido para un caso, ese caso se descarta (no se reporta
    como hallazgo): más vale un falso negativo puntual que arriesgar un
    falso positivo sin que LanguageTool ni el LLM lo hayan confirmado."""
    if not candidatos:
        return []

    prompt = _construir_prompt_lote(candidatos)
    texto_crudo = funcion_llm(prompt)
    por_indice = _parsear_json_lote(texto_crudo)

    hallazgos: list[HallazgoOrtografico] = []
    for indice, (segmento, coincidencia) in enumerate(candidatos):
        entrada = por_indice.get(indice)
        if not entrada or not entrada.get("es_error"):
            continue
        sugerencia = str(entrada.get("sugerencia") or "").strip()
        if not sugerencia:
            sugerencia = (
                coincidencia.sugerencias[0] if coincidencia.sugerencias else coincidencia.texto
            )
        explicacion = str(entrada.get("explicacion") or coincidencia.mensaje).strip()
        hallazgos.append(
            HallazgoOrtografico(
                severidad="media",
                ubicacion=segmento.ubicacion,
                descripcion=f"«{coincidencia.texto}»: {explicacion}",
                correccion_sugerida=sugerencia,
                texto_original=coincidencia.texto,
            )
        )
    return hallazgos


def revisar_segmentos(
    segmentos: list[SegmentoTexto],
    *,
    glosario: set[str],
    funcion_revisar_lt: FuncionRevisarLT,
    funcion_llm: FuncionLLM,
) -> list[HallazgoOrtografico]:
    """RN-06: cada `SegmentoTexto` (párrafo, celda, viñeta, etc. -- ver
    `parsers.segmentos`) pasa por LanguageTool; los términos del glosario del
    área y los números/códigos se excluyen antes de clasificar el resto en
    deterministas (van directo a hallazgo) o dudosos (se acumulan y se
    validan todos juntos con una sola llamada al LLM al final)."""
    glosario_normalizado = {t.strip().lower() for t in glosario}
    hallazgos: list[HallazgoOrtografico] = []
    candidatos_dudosos: list[tuple[SegmentoTexto, CoincidenciaLT]] = []

    for segmento in segmentos:
        for coincidencia in funcion_revisar_lt(segmento.texto):
            if _es_termino_de_glosario(coincidencia.texto, glosario_normalizado):
                continue
            if _es_numero_o_codigo(coincidencia.texto):
                continue
            if coincidencia.categoria in CATEGORIAS_DETERMINISTAS:
                hallazgos.append(_hallazgo_determinista(segmento, coincidencia))
            else:
                candidatos_dudosos.append((segmento, coincidencia))

    hallazgos += _validar_dudosos_con_llm(candidatos_dudosos, funcion_llm=funcion_llm)
    return hallazgos
