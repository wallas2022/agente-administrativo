"""Cliente HTTP de LanguageTool (RF-10, CU-05). Solo transporte -- RN-06
(exclusión por glosario) y la validación de casos dudosos con LLM viven en
`revision.py`, que recibe esta función inyectada (igual que `funcion_llm` /
`funcion_embedding` en `orquestador.pipeline_contable`) para no depender de
HTTP real en las pruebas unitarias.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class CoincidenciaLT:
    texto: str
    offset: int
    longitud: int
    mensaje: str
    sugerencias: list[str]
    regla_id: str
    categoria: str


def _url_base() -> str:
    host = os.environ.get("LANGUAGETOOL_HOST", "languagetool")
    puerto = os.environ.get("LANGUAGETOOL_PORT", "8010")
    return f"http://{host}:{puerto}"


TIMEOUT_POR_DEFECTO_S = 60.0


def _timeout_efectivo(timeout: float | None) -> float:
    """`LANGUAGETOOL_TIMEOUT_S` (60 s por defecto): la primera petición tras un rato sin uso
    tarda más (arranque en frío de la JVM) y 20 s fijos la hacían fallar."""
    if timeout is not None:
        return timeout
    try:
        valor = float(os.environ.get("LANGUAGETOOL_TIMEOUT_S", ""))
    except ValueError:
        return TIMEOUT_POR_DEFECTO_S
    return valor if valor > 0 else TIMEOUT_POR_DEFECTO_S


def revisar_texto(
    texto: str, *, idioma: str | None = None, timeout: float | None = None
) -> list[CoincidenciaLT]:
    idioma_efectivo = idioma or os.environ.get("LANGUAGETOOL_LOCALE", "es")
    respuesta = httpx.post(
        f"{_url_base()}/v2/check",
        data={"language": idioma_efectivo, "text": texto},
        timeout=_timeout_efectivo(timeout),
    )
    respuesta.raise_for_status()
    datos = respuesta.json()

    return [
        CoincidenciaLT(
            texto=texto[coincidencia["offset"] : coincidencia["offset"] + coincidencia["length"]],
            offset=coincidencia["offset"],
            longitud=coincidencia["length"],
            mensaje=coincidencia["message"],
            sugerencias=[r["value"] for r in coincidencia.get("replacements", [])],
            regla_id=coincidencia["rule"]["id"],
            categoria=coincidencia["rule"]["category"]["id"],
        )
        for coincidencia in datos.get("matches", [])
    ]
