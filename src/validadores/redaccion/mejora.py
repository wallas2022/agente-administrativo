"""Fase 2 de CU-02 (RF-07, RF-12): mejora de redacción por párrafo.

Pipeline por párrafo (streaming SSE, ver api/main.py):
  1. Ortografía (LanguageTool + glosario, reutilizando CU-05) -- solo
     correcciones tipográficas inequívocas (ver
     `validadores.redaccion.correccion_ortografica`).
  2. Formato determinista EST-001 (montos, fechas numéricas -- ver
     `validadores.redaccion.reglas.aplicar_formatos_deterministas`). El
     resultado de 1+2 es el "párrafo base": lo que se le pasa al LLM, y
     contra lo que se compara la guardia de integridad.
  3. (RF-07, rendimiento, 2026-10-01) Las dos opciones de estilo (Formal,
     Breve) se generan con una llamada CORTA cada una -- texto plano, sin
     pedirle motivos al LLM ni envolverlo en JSON -- en vez de una sola
     llamada pidiendo ambas opciones con motivos en un JSON. Medido contra
     gpt-oss:20b real: la llamada combinada tardaba 94-208s; una llamada
     de una sola opción, en texto plano, con `think="low"`, tardó 10-26s
     (ver docs/04-pruebas/resultados/local-cu02-rendimiento.md). Los
     "motivos" se calculan en Python comparando original vs. reescrito
     (`calcular_motivos`) -- más rápido y no depende de que el LLM los
     redacte bien.
  4. Guardia de integridad (RNF-03) por opción: si una opción cambia
     cifras/fechas/códigos/siglas/nombres propios respecto al párrafo
     base, se descarta esa opción (no todo el párrafo) -- puede aprobarse
     una y rechazarse la otra. Si ninguna pasa, se conserva el párrafo
     base tal cual ("sin cambio por seguridad").

Un párrafo corto (<25 palabras) sin ningún hallazgo de LanguageTool ni de
EST-001 se salta por completo (`puede_omitir_llm`) -- ya está bien tal
cual, no hace falta gastar una llamada al LLM en él.

Separado de la ruta HTTP para poder probarlo sin FastAPI, LanguageTool,
Qdrant ni Ollama reales -- mismo criterio que `validadores.contable.
explicacion`.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ortografia.cliente_languagetool import CoincidenciaLT
from parsers.segmentos import SegmentoTexto
from rag.busqueda import FuncionEmbedding, buscar_fragmentos, construir_citas
from validadores.redaccion.correccion_ortografica import corregir_ortografia_parrafo
from validadores.redaccion.guardia import verificar_integridad
from validadores.redaccion.reglas import aplicar_formatos_deterministas, validar_redaccion

FuncionLLM = Callable[[str], str]
FuncionRevisarLT = Callable[[str], list[CoincidenciaLT]]

ACCIONES_VALIDAS = frozenset({"corregir", "aclarar", "formalizar"})
ESTILOS = ("Formal", "Breve")

# Umbral de palabras del Bloque 4 (saltar LLM en párrafos cortos y limpios).
_PALABRAS_MINIMAS_PARA_LLM = 25

_INSTRUCCION_POR_ACCION = {
    "corregir": "Corrige la ortografía, gramática y puntuación del párrafo",
    "aclarar": "Reescribe el párrafo para que sea más claro y directo",
    "formalizar": "Reescribe el párrafo en un tono más formal e institucional",
}
_INSTRUCCION_POR_ESTILO = {
    "Formal": "en tono institucional, completo",
    "Breve": "de forma más directa y corta, sin perder información",
}


class _ClienteQdrant(Protocol):
    def collection_exists(self, coleccion: str) -> bool: ...


def puede_omitir_llm(
    parrafo: str, *, coincidencias_lt: list[CoincidenciaLT], tipo_documento: str
) -> bool:
    """Bloque 4 (rendimiento): un párrafo corto (<25 palabras) sin ningún
    hallazgo de LanguageTool ni de EST-001 ya está bien tal cual -- no hace
    falta gastar una llamada al LLM en él. `coincidencias_lt` se recibe ya
    calculado (no se vuelve a llamar a LanguageTool acá) porque quien
    orquesta (api/main.py) ya lo necesita para la fase de ortografía."""
    if len(parrafo.split()) >= _PALABRAS_MINIMAS_PARA_LLM:
        return False
    if coincidencias_lt:
        return False
    hallazgos_est001 = validar_redaccion(
        [SegmentoTexto(texto=parrafo, ubicacion="_")], tipo_documento=tipo_documento
    )
    return not hallazgos_est001


@dataclass(frozen=True)
class ParrafoPreparado:
    parrafo_base: str
    fuente_citada: str | None
    cita_estilo: str | None


def preparar_parrafo(
    parrafo: str,
    *,
    funcion_revisar_lt: FuncionRevisarLT,
    glosario: set[str],
    es_tabla: bool = False,
    cliente_qdrant: _ClienteQdrant | None = None,
    coleccion_rag: str | None = None,
    funcion_embedding: FuncionEmbedding | None = None,
) -> ParrafoPreparado:
    """Ortografía (LanguageTool + glosario) + formato EST-001, en ese
    orden -- el resultado es el "párrafo base" que se le pasa al LLM y
    contra el que se compara la guardia. `cliente_qdrant` es opcional: sin
    fuente de estilo vigente cargada (EST-001), la mejora corre igual pero
    sin "Regla aplicada"."""
    parrafo_con_ortografia = corregir_ortografia_parrafo(
        parrafo, glosario=glosario, funcion_revisar_lt=funcion_revisar_lt
    )
    parrafo_base = aplicar_formatos_deterministas(parrafo_con_ortografia, es_tabla=es_tabla)

    fuente_citada: str | None = None
    cita_estilo: str | None = None
    if cliente_qdrant is not None and coleccion_rag and funcion_embedding is not None:
        fragmentos = buscar_fragmentos(
            cliente_qdrant,  # type: ignore[arg-type]
            coleccion=coleccion_rag,
            texto_consulta=parrafo_base,
            funcion_embedding=funcion_embedding,
        )
        if fragmentos:
            fuente_citada, _referencia = construir_citas(fragmentos)
            cita_estilo = fragmentos[0].contenido

    return ParrafoPreparado(
        parrafo_base=parrafo_base, fuente_citada=fuente_citada, cita_estilo=cita_estilo
    )


def _construir_prompt_opcion(
    parrafo_base: str, *, accion: str, estilo: str, cita_estilo: str | None
) -> str:
    """Prompt corto y en texto plano (RF-07, rendimiento) -- sin JSON ni
    pedirle "motivos" al LLM, para minimizar los tokens de salida (y de
    paso el razonamiento interno del modelo, que escala con lo que tiene
    que producir). Los motivos se calculan en Python (`calcular_motivos`)."""
    instruccion_accion = _INSTRUCCION_POR_ACCION[accion]
    instruccion_estilo = _INSTRUCCION_POR_ESTILO[estilo]
    contexto_estilo = f"\nGuía de estilo aplicable:\n{cita_estilo}\n" if cita_estilo else ""
    return (
        "Eres un asistente de redacción institucional en español (es-GT).\n"
        f"{instruccion_accion}, reescribiéndolo {instruccion_estilo}.\n"
        "No cambies cifras, montos, fechas, códigos, siglas ni nombres propios. "
        "No agregues información nueva.\n"
        f"{contexto_estilo}"
        "Responde ÚNICAMENTE con el párrafo reescrito, sin comillas ni explicaciones.\n\n"
        f"Párrafo:\n{parrafo_base}"
    )


def _limpiar_respuesta_texto_plano(texto: str) -> str:
    limpio = texto.strip()
    if len(limpio) >= 2 and limpio[0] == limpio[-1] and limpio[0] in ('"', "'"):
        limpio = limpio[1:-1].strip()
    return limpio


_PATRON_PALABRA = re.compile(r"\w+", re.UNICODE)
_PATRON_FIN_ORACION = re.compile(r"[.!?]+")


def _sin_acentos(palabra: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", palabra)
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).lower()


def _contar_oraciones(texto: str) -> int:
    return len([o for o in _PATRON_FIN_ORACION.split(texto) if o.strip()])


def calcular_motivos(original: str, reescrito: str) -> list[str]:
    """Heurística de texto (no NLP): explica en términos generales qué
    cambió entre el párrafo base y la reescritura, sin pedírselo al LLM
    (RF-07, rendimiento -- ver docstring del módulo)."""
    palabras_originales = _PATRON_PALABRA.findall(original)
    palabras_nuevas = _PATRON_PALABRA.findall(reescrito)

    motivos: list[str] = []

    normalizadas_originales = {_sin_acentos(p) for p in palabras_originales}
    palabras_originales_exactas = set(palabras_originales)
    hubo_correccion_acentos = any(
        p not in palabras_originales_exactas and _sin_acentos(p) in normalizadas_originales
        for p in palabras_nuevas
    )
    if hubo_correccion_acentos:
        motivos.append("Se corrigieron acentos u ortografía")

    oraciones_originales = _contar_oraciones(original)
    oraciones_nuevas = _contar_oraciones(reescrito)
    if oraciones_nuevas > oraciones_originales:
        motivos.append("Se dividió una oración en varias")
    elif oraciones_nuevas < oraciones_originales:
        motivos.append("Se combinaron oraciones")

    if palabras_originales:
        proporcion = len(palabras_nuevas) / len(palabras_originales)
        if proporcion <= 0.85:
            motivos.append("Se acortó el texto, eliminando palabras redundantes")
        elif proporcion >= 1.15:
            motivos.append("Se amplió el texto")

    if not motivos:
        motivos.append("Cambios de redacción (orden de palabras, puntuación)")

    return motivos


@dataclass(frozen=True)
class OpcionMejora:
    estilo: str
    texto: str
    motivos: list[str]
    aprobada_guardia: bool
    razon_descarte: str | None


def generar_opcion(
    parrafo_base: str,
    *,
    accion: str,
    estilo: str,
    funcion_llm: FuncionLLM,
    cita_estilo: str | None = None,
) -> OpcionMejora | None:
    """Genera UNA opción de estilo (Formal o Breve). Devuelve `None` si el
    LLM no propuso ningún cambio real (texto igual al párrafo base) --
    igual que antes, "sin cambios" no es una opción a mostrar."""
    prompt = _construir_prompt_opcion(
        parrafo_base, accion=accion, estilo=estilo, cita_estilo=cita_estilo
    )
    texto_crudo = funcion_llm(prompt)
    texto = _limpiar_respuesta_texto_plano(texto_crudo)
    if not texto or texto.strip() == parrafo_base.strip():
        return None

    resultado_guardia = verificar_integridad(parrafo_base, texto)
    if not resultado_guardia.aprobado:
        return OpcionMejora(
            estilo=estilo,
            texto=texto,
            motivos=[],
            aprobada_guardia=False,
            razon_descarte=resultado_guardia.razon,
        )

    return OpcionMejora(
        estilo=estilo,
        texto=texto,
        motivos=calcular_motivos(parrafo_base, texto),
        aprobada_guardia=True,
        razon_descarte=None,
    )


@dataclass(frozen=True)
class ResultadoMejoraParrafo:
    parrafo_original: str
    # original + ortografía (LanguageTool) + formato EST-001 -- RNF-03:
    # nunca lo calcula/corrige el LLM, solo código determinista.
    parrafo_base: str
    ubicacion: str
    opciones: list[OpcionMejora]
    fuente_citada: str | None
    tiene_opciones_aprobadas: bool


def mejorar_parrafo(
    parrafo: str,
    *,
    ubicacion: str,
    accion: str,
    funcion_llm: FuncionLLM,
    funcion_revisar_lt: FuncionRevisarLT,
    glosario: set[str],
    es_tabla: bool = False,
    cliente_qdrant: _ClienteQdrant | None = None,
    coleccion_rag: str | None = None,
    funcion_embedding: FuncionEmbedding | None = None,
) -> ResultadoMejoraParrafo:
    """Envoltorio de conveniencia que arma el resultado completo de un
    párrafo (las dos opciones, ya resueltas) -- útil para pruebas y para
    cualquier llamador que no necesite la emisión incremental por opción.
    La ruta SSE real (api/main.py) usa `preparar_parrafo`/`generar_opcion`
    directamente para poder publicar "Formal" apenas está lista, sin
    esperar a "Breve" (Bloque 3, streaming escalonado)."""
    accion_normalizada = accion.strip().lower()
    if accion_normalizada not in ACCIONES_VALIDAS:
        raise ValueError(
            f"acción inválida: {accion!r} (debe ser una de {sorted(ACCIONES_VALIDAS)})"
        )

    preparado = preparar_parrafo(
        parrafo,
        funcion_revisar_lt=funcion_revisar_lt,
        glosario=glosario,
        es_tabla=es_tabla,
        cliente_qdrant=cliente_qdrant,
        coleccion_rag=coleccion_rag,
        funcion_embedding=funcion_embedding,
    )

    opciones: list[OpcionMejora] = []
    for estilo in ESTILOS:
        opcion = generar_opcion(
            preparado.parrafo_base,
            accion=accion_normalizada,
            estilo=estilo,
            funcion_llm=funcion_llm,
            cita_estilo=preparado.cita_estilo,
        )
        if opcion is not None:
            opciones.append(opcion)

    return ResultadoMejoraParrafo(
        parrafo_original=parrafo,
        parrafo_base=preparado.parrafo_base,
        ubicacion=ubicacion,
        opciones=opciones,
        fuente_citada=preparado.fuente_citada,
        tiene_opciones_aprobadas=any(o.aprobada_guardia for o in opciones),
    )
