"""Motor de revisión ortográfica (RF-10, RF-17, RN-06, CU-05, Bloques O2/O6).

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

RNF-04 (Bloque O6): la clasificación (`clasificar_segmentos`) es síncrona y
rápida (solo LanguageTool); la validación de los dudosos con LLM
(`validar_candidatos_con_llm`) es la parte lenta y corre aparte -- en
producción, en segundo plano (ver `orquestador.tareas`), para no bloquear
la publicación de los hallazgos deterministas.
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

# Regla propia (Bloque O6): LanguageTool marca cualquier mes con mayúscula
# inicial (regla "MIN_MESES", categoría "CASING") como error, sin distinguir
# un título/encabezado (donde SÍ es una convención tipográfica válida, p.
# ej. "Informe... — Agosto 2026") de una oración corrida. Encontrado en
# datos reales: docs/04-pruebas/resultados/local-S2.md documenta este
# mismo caso ("Agosto") como el único falso positivo de PP-03, y ni
# gpt-oss:20b ni llama3.2:3b lo descartaron de forma consistente (ver
# comparación de modelos en ese mismo archivo) -- se resuelve acá con una
# regla determinista, sin gastar una llamada al LLM.
_REGLA_MES_MAYUSCULA = "MIN_MESES"


@dataclass(frozen=True)
class HallazgoOrtografico:
    severidad: str
    ubicacion: str
    descripcion: str
    correccion_sugerida: str
    texto_original: str
    regla_codigo: str = "RN-06"


@dataclass(frozen=True)
class CandidatoDudoso:
    """Un caso que LanguageTool marcó pero que depende del contexto
    gramatical -- todavía sin confirmar. Se persiste como `Hallazgo` con
    `estado="en_validacion"` (ver `orquestador.pipeline_ortografia`) para
    que la UI lo muestre de inmediato, antes de que el LLM lo confirme o
    lo descarte."""

    ubicacion: str
    texto_original: str
    sugerencia_lt: str
    mensaje_lt: str
    regla_id: str


@dataclass(frozen=True)
class ResultadoValidacionDudoso:
    candidato: CandidatoDudoso
    es_error: bool
    correccion_sugerida: str
    explicacion: str


@dataclass(frozen=True)
class ResultadoClasificacion:
    deterministas: list[HallazgoOrtografico]
    dudosos: list[CandidatoDudoso]


def _es_termino_de_glosario(texto: str, glosario_normalizado: set[str]) -> bool:
    return texto.strip().lower() in glosario_normalizado


def _es_numero_o_codigo(texto: str) -> bool:
    return bool(_PATRON_SOLO_NUMERO_O_CODIGO.match(texto.strip()))


_UBICACIONES_EXACTAS_DE_TITULO = frozenset({"Párrafo 0", "Página 1, bloque 1"})
_PATRON_UBICACION_DE_TITULO = re.compile(
    r"^(Encabezado \d+,|Pie de página \d+,|Diapositiva \d+, título)"
)


def _es_ubicacion_de_titulo_o_encabezado(ubicacion: str) -> bool:
    if ubicacion in _UBICACIONES_EXACTAS_DE_TITULO:
        return True
    return bool(_PATRON_UBICACION_DE_TITULO.match(ubicacion))


def _es_mes_en_titulo_o_encabezado(coincidencia: CoincidenciaLT, ubicacion: str) -> bool:
    return coincidencia.regla_id == _REGLA_MES_MAYUSCULA and _es_ubicacion_de_titulo_o_encabezado(
        ubicacion
    )


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


def clasificar_segmentos(
    segmentos: list[SegmentoTexto], *, glosario: set[str], funcion_revisar_lt: FuncionRevisarLT
) -> ResultadoClasificacion:
    """Fase 1 (RNF-04, Bloque O6): solo LanguageTool -- rápida, sin LLM.
    Los términos del glosario del área, los números/códigos y los meses en
    mayúscula dentro de un título/encabezado se excluyen antes de
    clasificar el resto en deterministas (listos como hallazgo) o dudosos
    (todavía sin confirmar)."""
    glosario_normalizado = {t.strip().lower() for t in glosario}
    deterministas: list[HallazgoOrtografico] = []
    dudosos: list[CandidatoDudoso] = []

    for segmento in segmentos:
        for coincidencia in funcion_revisar_lt(segmento.texto):
            if _es_termino_de_glosario(coincidencia.texto, glosario_normalizado):
                continue
            if _es_numero_o_codigo(coincidencia.texto):
                continue
            if _es_mes_en_titulo_o_encabezado(coincidencia, segmento.ubicacion):
                continue
            if coincidencia.categoria in CATEGORIAS_DETERMINISTAS:
                deterministas.append(_hallazgo_determinista(segmento, coincidencia))
            else:
                sugerencia = (
                    coincidencia.sugerencias[0] if coincidencia.sugerencias else coincidencia.texto
                )
                dudosos.append(
                    CandidatoDudoso(
                        ubicacion=segmento.ubicacion,
                        texto_original=coincidencia.texto,
                        sugerencia_lt=sugerencia,
                        mensaje_lt=coincidencia.mensaje,
                        regla_id=coincidencia.regla_id,
                    )
                )

    return ResultadoClasificacion(deterministas=deterministas, dudosos=dudosos)


def _construir_prompt_lote(
    candidatos: list[CandidatoDudoso], contexto_por_ubicacion: dict[str, str]
) -> str:
    bloques = []
    for indice, candidato in enumerate(candidatos):
        contexto = contexto_por_ubicacion.get(candidato.ubicacion, candidato.texto_original)
        bloques.append(
            f"### Caso {indice}\n"
            f"- Contexto: {contexto}\n"
            f'- Fragmento marcado: "{candidato.texto_original}"\n'
            f"- Regla que lo marcó: {candidato.regla_id} ({candidato.mensaje_lt})\n"
            f'- Sugerencia de LanguageTool: "{candidato.sugerencia_lt}"'
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


def validar_candidatos_con_llm(
    candidatos: list[CandidatoDudoso],
    *,
    contexto_por_ubicacion: dict[str, str],
    funcion_llm: FuncionLLM,
) -> list[ResultadoValidacionDudoso]:
    """Fase 2 (RNF-04, Bloque O6): una sola llamada al LLM para todos los
    casos dudosos de un documento -- corre aparte de la clasificación
    (`clasificar_segmentos`), típicamente en segundo plano. Si el LLM no
    responde JSON válido para un caso, se descarta (es_error=False): más
    vale un falso negativo puntual que arriesgar un falso positivo sin que
    LanguageTool ni el LLM lo hayan confirmado."""
    if not candidatos:
        return []

    prompt = _construir_prompt_lote(candidatos, contexto_por_ubicacion)
    texto_crudo = funcion_llm(prompt)
    por_indice = _parsear_json_lote(texto_crudo)

    resultados: list[ResultadoValidacionDudoso] = []
    for indice, candidato in enumerate(candidatos):
        entrada = por_indice.get(indice)
        es_error = bool(entrada and entrada.get("es_error"))
        sugerencia = str(entrada.get("sugerencia") or "").strip() if entrada else ""
        if not sugerencia:
            sugerencia = candidato.sugerencia_lt
        explicacion = str(entrada.get("explicacion") or "").strip() if entrada else ""
        if not explicacion:
            explicacion = candidato.mensaje_lt
        resultados.append(
            ResultadoValidacionDudoso(
                candidato=candidato,
                es_error=es_error,
                correccion_sugerida=sugerencia,
                explicacion=explicacion,
            )
        )
    return resultados


def revisar_segmentos(
    segmentos: list[SegmentoTexto],
    *,
    glosario: set[str],
    funcion_revisar_lt: FuncionRevisarLT,
    funcion_llm: FuncionLLM,
) -> list[HallazgoOrtografico]:
    """Atajo síncrono (clasificar + validar dudosos en un solo paso) para
    quien no necesita las dos fases por separado -- pruebas y mediciones
    (PP-03, Bloque O5/O6). En producción, `orquestador.tareas` usa
    `clasificar_segmentos` y `validar_candidatos_con_llm` por separado
    (RNF-04, Bloque O6)."""
    clasificacion = clasificar_segmentos(
        segmentos, glosario=glosario, funcion_revisar_lt=funcion_revisar_lt
    )
    contexto_por_ubicacion = {s.ubicacion: s.texto for s in segmentos}
    resultados = validar_candidatos_con_llm(
        clasificacion.dudosos,
        contexto_por_ubicacion=contexto_por_ubicacion,
        funcion_llm=funcion_llm,
    )

    hallazgos = list(clasificacion.deterministas)
    for resultado in resultados:
        if not resultado.es_error:
            continue
        hallazgos.append(
            HallazgoOrtografico(
                severidad="media",
                ubicacion=resultado.candidato.ubicacion,
                descripcion=f"«{resultado.candidato.texto_original}»: {resultado.explicacion}",
                correccion_sugerida=resultado.correccion_sugerida,
                texto_original=resultado.candidato.texto_original,
            )
        )
    return hallazgos
