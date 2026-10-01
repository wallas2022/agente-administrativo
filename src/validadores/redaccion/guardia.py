"""Guardia anti-alteración de cifras, fechas y nombres propios (CU-02) --
ver docs/02-analisis/02-analisis-cu02-redaccion-amigable.md §2.3.

A diferencia de CU-01 (RNF-03: el LLM nunca calcula, solo redacta sobre
cifras ya calculadas por Python), en CU-02 el LLM sí genera el contenido
del párrafo -- por eso esta guardia compara, DESPUÉS de la llamada al LLM,
que el párrafo sugerido no haya alterado ningún número, fecha o nombre
propio del original. Si algo no coincide exactamente, la fase 2
(`orquestador.pipeline_redaccion`) descarta la sugerencia y conserva el
original, marcando el hallazgo `estado="sin_cambio_por_seguridad"`.

Heurística de texto (regex), no NLP real -- en particular la detección de
"nombres propios" (palabra con mayúscula inicial que no abre oración)
puede fallar: no detecta un nombre propio que SÍ abre una oración (falso
negativo) y puede contar como nombre una palabra en mayúscula por énfasis
que no lo es (falso positivo) -- en ambos casos el efecto es conservador
(más propenso a descartar una sugerencia válida que a dejar pasar una
alterada), documentado explícitamente en
docs/02-analisis/02-analisis-cu02-redaccion-amigable.md §4.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Primero intenta la forma "agrupada de a 3" (1,250 / 1,250.00) para no
# confundir una coma de miles real con una coma de puntuación que por
# casualidad sigue a un número (p. ej. "2026, Juan" no debe capturar la
# coma); si no calza esa forma, cae a un número suelto con decimal opcional.
_PATRON_NUMERO = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
_PATRON_FECHA = re.compile(
    r"\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}"
    r"|\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}\s+de\s+[a-záéíóúñ]+(?:\s+de\s+\d{2,4})?",
    re.IGNORECASE,
)
_PATRON_PALABRA = re.compile(r"[A-Za-záéíóúñÁÉÍÓÚÑ]+")
_PATRON_FIN_ORACION = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class ResultadoGuardia:
    aprobado: bool
    razon: str | None = None


def _nombres_propios(texto: str) -> set[str]:
    nombres: set[str] = set()
    for oracion in _PATRON_FIN_ORACION.split(texto):
        palabras = _PATRON_PALABRA.findall(oracion)
        for palabra in palabras[1:]:  # se salta la primera palabra de cada oración
            if palabra[:1].isupper():
                nombres.add(palabra)
    return nombres


def verificar_integridad(original: str, sugerido: str) -> ResultadoGuardia:
    """Compara original vs. sugerido; aprueba solo si cifras, fechas y
    nombres propios son exactamente los mismos conjuntos (el orden y la
    redacción alrededor sí pueden cambiar -- eso es lo que CU-02 mejora)."""
    # Fechas antes que números: una fecha también está hecha de dígitos, así
    # que si cambia, también rompería la comparación de números -- se
    # verifica primero para que el motivo reportado sea el más específico.
    fechas_original = {m.strip() for m in _PATRON_FECHA.findall(original)}
    fechas_sugerido = {m.strip() for m in _PATRON_FECHA.findall(sugerido)}
    if fechas_original != fechas_sugerido:
        return ResultadoGuardia(
            aprobado=False,
            razon="Las fechas del párrafo sugerido no coinciden con el original",
        )

    numeros_original = set(_PATRON_NUMERO.findall(original))
    numeros_sugerido = set(_PATRON_NUMERO.findall(sugerido))
    if numeros_original != numeros_sugerido:
        return ResultadoGuardia(
            aprobado=False,
            razon="Las cifras del párrafo sugerido no coinciden con el original",
        )

    nombres_original = _nombres_propios(original)
    nombres_sugerido = _nombres_propios(sugerido)
    if nombres_original != nombres_sugerido:
        return ResultadoGuardia(
            aprobado=False,
            razon="Los nombres propios del párrafo sugerido no coinciden con el original",
        )

    return ResultadoGuardia(aprobado=True)
