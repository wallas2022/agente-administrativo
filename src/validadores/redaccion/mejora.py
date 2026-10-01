"""Fase 2 de CU-02 (RF-07, RF-12): mejora de redacción por párrafo.

Pipeline por párrafo (streaming SSE, ver api/main.py):
  1. Ortografía (LanguageTool + glosario, reutilizando CU-05) -- solo
     correcciones tipográficas inequívocas (ver
     `validadores.redaccion.correccion_ortografica`).
  2. Formato determinista EST-001 (montos, fechas numéricas -- ver
     `validadores.redaccion.reglas.aplicar_formatos_deterministas`). El
     resultado de 1+2 es el "párrafo base": lo que se le pasa al LLM, y
     contra lo que se compara la guardia de integridad (nunca contra el
     párrafo original crudo, que todavía podía tener errores de formato).
  3. LLM (temperature=0, seed fija, format=json) devuelve hasta 2 opciones
     de estilo (Formal/Breve) con sus motivos.
  4. Guardia de integridad (RNF-03) por opción: si una opción cambia
     cifras/fechas/nombres propios respecto al párrafo base, se descarta
     esa opción (no todo el párrafo) -- puede aprobarse una y rechazarse
     la otra. Si ninguna pasa, se conserva el párrafo base tal cual ("sin
     cambio por seguridad").

Separado de la ruta HTTP para poder probarlo sin FastAPI, LanguageTool,
Qdrant ni Ollama reales -- mismo criterio que `validadores.contable.
explicacion`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ortografia.cliente_languagetool import CoincidenciaLT
from rag.busqueda import FuncionEmbedding, buscar_fragmentos, construir_citas
from validadores.redaccion.correccion_ortografica import corregir_ortografia_parrafo
from validadores.redaccion.guardia import verificar_integridad
from validadores.redaccion.reglas import aplicar_formatos_deterministas

FuncionLLM = Callable[[str], str]
FuncionRevisarLT = Callable[[str], list[CoincidenciaLT]]

ACCIONES_VALIDAS = frozenset({"corregir", "aclarar", "formalizar"})

_INSTRUCCION_POR_ACCION = {
    "corregir": (
        "Corrige la ortografía, gramática y puntuación del párrafo, "
        "sin cambiar su significado ni su tono."
    ),
    "aclarar": "Reescribe el párrafo para que sea más claro y directo, sin cambiar su significado.",
    "formalizar": (
        "Reescribe el párrafo en un tono más formal e institucional, "
        "sin cambiar su significado."
    ),
}


class _ClienteQdrant(Protocol):
    def collection_exists(self, coleccion: str) -> bool: ...


def _construir_prompt(parrafo_base: str, *, accion: str, cita_estilo: str | None) -> str:
    instruccion = _INSTRUCCION_POR_ACCION[accion]
    contexto_estilo = f"\nGuía de estilo aplicable:\n{cita_estilo}\n" if cita_estilo else ""
    return (
        "Eres un asistente de redacción de documentos institucionales en español (es-GT).\n"
        f"{instruccion}\n"
        "Propón DOS versiones del párrafo:\n"
        '  1) "Formal": tono institucional, completo.\n'
        '  2) "Breve": más directa y corta, sin perder información.\n'
        "IMPORTANTE: no agregues, quites ni cambies cifras, montos, fechas, códigos ni "
        "nombres propios -- deben quedar EXACTAMENTE igual que en el párrafo original, "
        "aunque cambie el orden de las palabras a su alrededor. No inventes el "
        "significado de siglas; déjalas como están. No agregues información nueva.\n"
        f"{contexto_estilo}"
        "Responde ÚNICAMENTE con un objeto JSON válido, con este formato exacto: "
        '{"opciones": [{"estilo": "Formal", "texto": "...", "motivos": ["..."]}, '
        '{"estilo": "Breve", "texto": "...", "motivos": ["..."]}]}\n\n'
        f"Párrafo:\n{parrafo_base}"
    )


@dataclass(frozen=True)
class _OpcionCruda:
    estilo: str
    texto: str
    motivos: list[str]


def _parsear_respuesta(texto_crudo: str) -> list[_OpcionCruda]:
    """Tolera que el modelo envuelva el JSON en texto o en un bloque de
    código ```json ... ``` -- mismo criterio que
    `validadores.contable.explicacion._parsear_json_lote`. Devuelve lista
    vacía (nunca excepción) ante cualquier respuesta mal formada: el
    llamador trata "sin opciones" igual que "ninguna opción pasó la
    guardia" (se conserva el párrafo base)."""
    candidato = texto_crudo.strip()
    coincidencia = re.search(r"\{.*\}", candidato, re.DOTALL)
    if coincidencia:
        candidato = coincidencia.group(0)
    try:
        datos = json.loads(candidato)
    except json.JSONDecodeError:
        return []
    if not isinstance(datos, dict):
        return []
    opciones_crudas = datos.get("opciones")
    if not isinstance(opciones_crudas, list):
        return []

    opciones: list[_OpcionCruda] = []
    for opcion in opciones_crudas[:2]:
        if not isinstance(opcion, dict):
            continue
        estilo = opcion.get("estilo")
        texto = opcion.get("texto")
        motivos = opcion.get("motivos")
        if not isinstance(estilo, str) or not isinstance(texto, str) or not texto.strip():
            continue
        motivos_validos = (
            [m for m in motivos if isinstance(m, str)] if isinstance(motivos, list) else []
        )
        opciones.append(_OpcionCruda(estilo=estilo, texto=texto, motivos=motivos_validos))
    return opciones


@dataclass(frozen=True)
class OpcionMejora:
    estilo: str
    texto: str
    motivos: list[str]
    aprobada_guardia: bool
    razon_descarte: str | None


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
    """Punto de entrada de la fase 2 para UN párrafo. `cliente_qdrant` es
    opcional: sin fuente de estilo vigente cargada (EST-001, ver §2.4 del
    análisis), la mejora corre igual pero sin "Regla aplicada"."""
    accion_normalizada = accion.strip().lower()
    if accion_normalizada not in ACCIONES_VALIDAS:
        raise ValueError(
            f"acción inválida: {accion!r} (debe ser una de {sorted(ACCIONES_VALIDAS)})"
        )

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

    prompt = _construir_prompt(parrafo_base, accion=accion_normalizada, cita_estilo=cita_estilo)
    texto_crudo = funcion_llm(prompt)
    opciones_crudas = _parsear_respuesta(texto_crudo)

    opciones: list[OpcionMejora] = []
    for opcion_cruda in opciones_crudas:
        if opcion_cruda.texto.strip() == parrafo_base.strip():
            continue  # "sin cambios" no es una opción real a mostrar
        resultado_guardia = verificar_integridad(parrafo_base, opcion_cruda.texto)
        opciones.append(
            OpcionMejora(
                estilo=opcion_cruda.estilo,
                texto=opcion_cruda.texto,
                motivos=opcion_cruda.motivos,
                aprobada_guardia=resultado_guardia.aprobado,
                razon_descarte=None if resultado_guardia.aprobado else resultado_guardia.razon,
            )
        )

    return ResultadoMejoraParrafo(
        parrafo_original=parrafo,
        parrafo_base=parrafo_base,
        ubicacion=ubicacion,
        opciones=opciones,
        fuente_citada=fuente_citada,
        tiene_opciones_aprobadas=any(o.aprobada_guardia for o in opciones),
    )
