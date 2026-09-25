"""Redacción de la causa probable y corrección sugerida de un hallazgo
contable (RF-12, CU-01, paso 5 de Sprint 1).

RNF-03: el cálculo (severidad, ubicación, monto) ya lo hizo
`validadores.contable.reglas`; aquí solo se redacta la explicación en
lenguaje natural citando la fuente recuperada por RAG.

Para no disparar una llamada al LLM por cada hallazgo (con un documento de
varias decenas de hallazgos esto tardaba 20-40 min con gpt-oss:20b,
incumpliendo RNF-04 — ver docs/04-pruebas/resultados/local-S1.md):

- RN-02, RN-03, RN-04 y RN-FORMULA se explican por PLANTILLA, sin LLM: su
  causa es mecánica y ya está descrita en `HallazgoDetectado.descripcion`.
  RN-03 y RN-04 además se agrupan en una sola explicación por regla — todas
  las partidas fuera de período (o todas las duplicadas) comparten la misma
  causa, así que no tiene sentido redactarla una vez por partida.
- Solo RN-01 (descuadre) y RN-05 (mezcla de moneda) necesitan redacción con
  LLM, y se agrupan en una ÚNICA llamada (el modelo responde con un JSON,
  un objeto por hallazgo) en vez de una llamada por hallazgo.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass

from rag.busqueda import ResultadoBusqueda
from validadores.contable.reglas import HallazgoDetectado

VERSION_PROMPT_LOTE = "redaccion-contable-lote.v1"
VERSION_PLANTILLA = "plantilla.v1"

FuncionLLM = Callable[[str], str]

# RN-01 (descuadre) y RN-05 (mezcla de moneda): la causa varía por hallazgo
# (montos y monedas distintos), no se puede resolver con una plantilla fija.
REGLAS_CON_LLM = frozenset({"RN-01", "RN-05"})
# RN-03 y RN-04: la causa es la misma para todas las partidas del grupo.
REGLAS_AGRUPADAS = frozenset({"RN-03", "RN-04"})


@dataclass(frozen=True)
class ExplicacionGenerada:
    texto: str
    modelo_llm: str | None  # None cuando la explicación es por plantilla (sin LLM)
    version_prompt: str
    fuente_citada: str | None


def _formatear(causa_probable: str, correccion_sugerida: str) -> str:
    return (
        f"**Causa probable**\n\n{causa_probable}\n\n"
        f"**Corrección sugerida**\n\n{correccion_sugerida}"
    )


def _cita(fragmentos: list[ResultadoBusqueda]) -> str:
    return f" [{fragmentos[0].fuente_id}]" if fragmentos else ""


_CORRECCION_POR_REGLA: dict[str, str] = {
    "RN-02": (
        "Verifica el código de cuenta en el catálogo de cuentas vigente y corrige "
        "la partida para usar una cuenta existente."
    ),
    "RN-03": (
        "Confirma si la partida corresponde a un ajuste de cierre debidamente "
        "documentado; si no, corrige la fecha para que quede dentro del período "
        "que se está cerrando."
    ),
    "RN-04": (
        "Revisa las partidas señaladas y, si se trata de un registro duplicado "
        "real, elimina o corrige la que no corresponda."
    ),
    "RN-FORMULA": (
        "Reemplaza el valor fijo de la fila de totales por una fórmula de suma "
        "(=SUMA(...)) que se recalcule automáticamente."
    ),
}


def generar_explicacion_plantilla(
    hallazgo: HallazgoDetectado, fragmentos: list[ResultadoBusqueda]
) -> ExplicacionGenerada:
    """RN-02 y RN-FORMULA: una plantilla por hallazgo — cada uno referencia
    una cuenta o celda distinta, no tiene sentido agruparlos."""
    correccion = _CORRECCION_POR_REGLA.get(
        hallazgo.regla_codigo, "Revisar manualmente este hallazgo."
    )
    texto = _formatear(f"{hallazgo.descripcion}{_cita(fragmentos)}", correccion)
    return ExplicacionGenerada(
        texto=texto,
        modelo_llm=None,
        version_prompt=VERSION_PLANTILLA,
        fuente_citada=fragmentos[0].fuente_id if fragmentos else None,
    )


def generar_explicacion_plantilla_grupo(
    hallazgos: list[HallazgoDetectado], fragmentos: list[ResultadoBusqueda]
) -> ExplicacionGenerada:
    """RN-03 y RN-04: todas las partidas del grupo comparten la misma causa
    (fecha fuera de período / posible duplicado) — una sola explicación para
    todo el grupo en vez de repetir el mismo texto por cada partida."""
    ubicaciones = ", ".join(h.ubicacion for h in hallazgos)
    causa = f"{hallazgos[0].descripcion} Afecta a: {ubicaciones}.{_cita(fragmentos)}"
    correccion = _CORRECCION_POR_REGLA.get(
        hallazgos[0].regla_codigo, "Revisar manualmente estos hallazgos."
    )
    texto = _formatear(causa, correccion)
    return ExplicacionGenerada(
        texto=texto,
        modelo_llm=None,
        version_prompt=VERSION_PLANTILLA,
        fuente_citada=fragmentos[0].fuente_id if fragmentos else None,
    )


def construir_prompt_lote(
    items: list[tuple[HallazgoDetectado, list[ResultadoBusqueda]]],
) -> str:
    bloques = []
    for indice, (hallazgo, fragmentos) in enumerate(items):
        contexto_fuente = (
            "\n".join(f"[{f.fuente_id}] {f.contenido}" for f in fragmentos)
            if fragmentos
            else "(sin fuente recuperada para este hallazgo)"
        )
        bloques.append(
            f"### Hallazgo {indice}\n"
            f"- Regla: {hallazgo.regla_codigo}\n- Severidad: {hallazgo.severidad}\n"
            f"- Ubicación: {hallazgo.ubicacion}\n- Descripción: {hallazgo.descripcion}\n"
            f"- Monto: {hallazgo.monto if hallazgo.monto is not None else 'N/A'}\n"
            f"- Moneda: {hallazgo.moneda or 'N/A'}\n"
            f"- Fuente(s) de conocimiento:\n{contexto_fuente}"
        )
    return (
        "Eres un asistente que ayuda a revisar documentos contables en español (es-GT).\n"
        "Se te dan varios hallazgos YA DETECTADOS por código determinista (regla, "
        "severidad, ubicación y monto ya calculados). Para CADA uno, redacta una causa "
        "probable y una corrección sugerida breves.\n\n"
        "IMPORTANTE: no calcules ni inventes cifras, fechas o cuentas nuevas; usa solo "
        "los datos de cada hallazgo. Si citas una fuente, menciona su identificador "
        "entre corchetes tal como aparece en el bloque de ese hallazgo.\n\n"
        "Responde ÚNICAMENTE con un arreglo JSON válido (sin texto antes ni después, "
        "sin bloque de código), con exactamente este formato:\n"
        '[{"indice": 0, "causa_probable": "...", "correccion_sugerida": "..."}, ...]\n\n'
        + "\n\n".join(bloques)
    )


def _parsear_json_lote(texto_crudo: str) -> dict[int, dict[str, str]]:
    """Tolera que el modelo envuelva el JSON en texto o en un bloque de
    código ```json ... ``` — si no logra parsear nada, devuelve {} y cada
    hallazgo cae al texto de respaldo (no se reintenta la llamada: ya se
    hizo lo posible por no volver a pagar el costo de otra ronda de LLM)."""
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

    resultado: dict[int, dict[str, str]] = {}
    for entrada in datos:
        if not isinstance(entrada, dict) or "indice" not in entrada:
            continue
        try:
            indice = int(entrada["indice"])
        except (TypeError, ValueError):
            continue
        resultado[indice] = {
            "causa_probable": str(entrada.get("causa_probable", "")).strip(),
            "correccion_sugerida": str(entrada.get("correccion_sugerida", "")).strip(),
        }
    return resultado


def _explicacion_de_respaldo(
    hallazgo: HallazgoDetectado, fragmentos: list[ResultadoBusqueda]
) -> str:
    return _formatear(
        f"{hallazgo.descripcion}{_cita(fragmentos)}",
        "No se pudo generar una corrección automática esta vez; revisar manualmente "
        "este hallazgo.",
    )


def generar_explicaciones_lote(
    items: list[tuple[HallazgoDetectado, list[ResultadoBusqueda]]],
    *,
    funcion_llm: FuncionLLM,
    modelo: str,
) -> list[ExplicacionGenerada]:
    """RN-01 y RN-05: una sola llamada al LLM para todos los hallazgos que la
    necesitan, en vez de una por hallazgo — el costo dominante del pipeline
    (ver docs/04-pruebas/resultados/local-S1.md) es el número de llamadas al
    LLM, no el tamaño de cada una."""
    if not items:
        return []

    prompt = construir_prompt_lote(items)
    texto_crudo = funcion_llm(prompt)
    por_indice = _parsear_json_lote(texto_crudo)

    explicaciones: list[ExplicacionGenerada] = []
    for indice, (hallazgo, fragmentos) in enumerate(items):
        entrada = por_indice.get(indice)
        fuente_citada = fragmentos[0].fuente_id if fragmentos else None
        if entrada and entrada["causa_probable"] and entrada["correccion_sugerida"]:
            texto = _formatear(entrada["causa_probable"], entrada["correccion_sugerida"])
        else:
            texto = _explicacion_de_respaldo(hallazgo, fragmentos)
        explicaciones.append(
            ExplicacionGenerada(
                texto=texto,
                modelo_llm=modelo,
                version_prompt=VERSION_PROMPT_LOTE,
                fuente_citada=fuente_citada,
            )
        )
    return explicaciones
