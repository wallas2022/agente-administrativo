"""Fase 2 de CU-02 (RF-07, RF-12): mejora de redacción por párrafo -- una
llamada al LLM por párrafo (no por lote, a diferencia de CU-01/CU-05) para
poder transmitir cada resultado por streaming SSE apenas está listo (ver
docs/02-analisis/02-analisis-cu02-redaccion-amigable.md §2.1-§2.3 y la ruta
SSE en api/main.py).

Separado de la ruta HTTP para poder probarlo sin FastAPI ni Qdrant reales
-- mismo criterio que `validadores.contable.explicacion`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from rag.busqueda import FuncionEmbedding, buscar_fragmentos, construir_citas
from validadores.redaccion.guardia import verificar_integridad

FuncionLLM = Callable[[str], str]

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


def _construir_prompt(parrafo: str, *, accion: str, cita_estilo: str | None) -> str:
    instruccion = _INSTRUCCION_POR_ACCION[accion]
    contexto_estilo = f"\nGuía de estilo aplicable:\n{cita_estilo}\n" if cita_estilo else ""
    return (
        "Eres un asistente de redacción de documentos institucionales en español (es-GT).\n"
        f"{instruccion}\n"
        "IMPORTANTE: no agregues, quites ni cambies cifras, montos, fechas o nombres "
        "propios -- deben quedar EXACTAMENTE igual que en el párrafo original, aunque "
        "cambie el orden de las palabras a su alrededor. Si el párrafo ya está bien así, "
        "devuélvelo sin cambios.\n"
        f"{contexto_estilo}"
        "Responde ÚNICAMENTE con un objeto JSON válido (sin texto antes ni después, sin "
        'bloque de código), con este formato exacto: {"parrafo_sugerido": "..."}\n\n'
        f"Párrafo original:\n{parrafo}"
    )


def _parsear_respuesta(texto_crudo: str) -> str | None:
    """Tolera que el modelo envuelva el JSON en texto o en un bloque de
    código ```json ... ``` -- mismo criterio que
    validadores.contable.explicacion._parsear_json_lote."""
    candidato = texto_crudo.strip()
    coincidencia = re.search(r"\{.*\}", candidato, re.DOTALL)
    if coincidencia:
        candidato = coincidencia.group(0)
    try:
        datos = json.loads(candidato)
    except json.JSONDecodeError:
        return None
    if not isinstance(datos, dict):
        return None
    sugerido = datos.get("parrafo_sugerido")
    return sugerido if isinstance(sugerido, str) else None


@dataclass(frozen=True)
class ResultadoMejoraParrafo:
    parrafo_original: str
    ubicacion: str
    tiene_sugerencia: bool
    parrafo_sugerido: str | None
    fuente_citada: str | None
    descartado_por_guardia: bool
    razon_descarte: str | None


def mejorar_parrafo(
    parrafo: str,
    *,
    ubicacion: str,
    accion: str,
    funcion_llm: FuncionLLM,
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

    fuente_citada: str | None = None
    cita_estilo: str | None = None
    if cliente_qdrant is not None and coleccion_rag and funcion_embedding is not None:
        fragmentos = buscar_fragmentos(
            cliente_qdrant,  # type: ignore[arg-type]
            coleccion=coleccion_rag,
            texto_consulta=parrafo,
            funcion_embedding=funcion_embedding,
        )
        if fragmentos:
            fuente_citada, _referencia = construir_citas(fragmentos)
            cita_estilo = fragmentos[0].contenido

    prompt = _construir_prompt(parrafo, accion=accion_normalizada, cita_estilo=cita_estilo)
    texto_crudo = funcion_llm(prompt)
    sugerido = _parsear_respuesta(texto_crudo)

    sin_cambio = sugerido is None or sugerido.strip() == parrafo.strip()
    if sin_cambio:
        return ResultadoMejoraParrafo(
            parrafo_original=parrafo,
            ubicacion=ubicacion,
            tiene_sugerencia=False,
            parrafo_sugerido=None,
            fuente_citada=None,
            descartado_por_guardia=False,
            razon_descarte=None,
        )

    assert sugerido is not None  # para mypy: sin_cambio ya descartó el caso None
    resultado_guardia = verificar_integridad(parrafo, sugerido)
    if not resultado_guardia.aprobado:
        return ResultadoMejoraParrafo(
            parrafo_original=parrafo,
            ubicacion=ubicacion,
            tiene_sugerencia=False,
            parrafo_sugerido=None,
            fuente_citada=None,
            descartado_por_guardia=True,
            razon_descarte=resultado_guardia.razon,
        )

    return ResultadoMejoraParrafo(
        parrafo_original=parrafo,
        ubicacion=ubicacion,
        tiene_sugerencia=True,
        parrafo_sugerido=sugerido,
        fuente_citada=fuente_citada,
        descartado_por_guardia=False,
        razon_descarte=None,
    )
