"""Redacción de la causa probable y corrección sugerida de un hallazgo
contable con el LLM (RF-12, CU-01, paso 5 de Sprint 1).

RNF-03: el LLM **no calcula nada** — el hallazgo (severidad, ubicación,
monto) ya viene calculado por `validadores.contable.reglas`. El LLM solo
redacta una explicación en lenguaje natural citando la fuente recuperada por
RAG. El prompt está versionado (`VERSION_PROMPT`) para trazabilidad (RNF-06):
cada explicación generada debe guardar `modelo_llm` y `version_prompt` en el
`Analisis`/`Hallazgo` correspondiente.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from rag.busqueda import ResultadoBusqueda
from validadores.contable.reglas import HallazgoDetectado

VERSION_PROMPT = "redaccion-contable.v1"

FuncionLLM = Callable[[str], str]


@dataclass(frozen=True)
class ExplicacionGenerada:
    texto: str
    modelo_llm: str
    version_prompt: str
    fuente_citada: str | None


def construir_prompt(hallazgo: HallazgoDetectado, fragmentos: list[ResultadoBusqueda]) -> str:
    contexto_fuente = (
        "\n\n".join(f"[{f.fuente_id}] {f.contenido}" for f in fragmentos)
        if fragmentos
        else "(sin fuente recuperada para este hallazgo)"
    )
    return (
        "Eres un asistente que ayuda a revisar documentos contables en español (es-GT).\n"
        "Se te da un hallazgo YA DETECTADO por código determinista (regla, severidad, "
        "ubicación y monto ya calculados) y fragmentos de la base de conocimiento que lo "
        "respaldan. Tu única tarea es redactar, en dos partes breves:\n"
        "1) Causa probable\n"
        "2) Corrección sugerida\n\n"
        "IMPORTANTE: no calcules ni inventes cifras, fechas o cuentas nuevas; usa solo "
        "los datos del hallazgo. Si citas la fuente, menciona su identificador entre "
        "corchetes tal como aparece abajo.\n\n"
        f"Hallazgo:\n- Regla: {hallazgo.regla_codigo}\n- Severidad: {hallazgo.severidad}\n"
        f"- Ubicación: {hallazgo.ubicacion}\n- Descripción: {hallazgo.descripcion}\n"
        f"- Monto: {hallazgo.monto if hallazgo.monto is not None else 'N/A'}\n"
        f"- Moneda: {hallazgo.moneda or 'N/A'}\n\n"
        f"Fuente(s) de conocimiento:\n{contexto_fuente}"
    )


def generar_explicacion(
    hallazgo: HallazgoDetectado,
    fragmentos: list[ResultadoBusqueda],
    *,
    funcion_llm: FuncionLLM,
    modelo: str,
) -> ExplicacionGenerada:
    prompt = construir_prompt(hallazgo, fragmentos)
    texto = funcion_llm(prompt)
    fuente_citada = fragmentos[0].fuente_id if fragmentos else None
    return ExplicacionGenerada(
        texto=texto,
        modelo_llm=modelo,
        version_prompt=VERSION_PROMPT,
        fuente_citada=fuente_citada,
    )
