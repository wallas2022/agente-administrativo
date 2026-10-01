"""Corrección ortográfica determinista por párrafo (CU-02, fase 2): reutiliza
LanguageTool + el glosario interno de CU-05 (`ortografia.cliente_languagetool`,
`comun.glosario`) antes de pasar el párrafo a las reglas EST-001 y al LLM.

Solo se aplican automáticamente las coincidencias de categoría "TYPOS" (error
tipográfico claro, con al menos una sugerencia) -- a diferencia de
`ortografia.revision` (CU-05), acá no hay un paso de confirmación por LLM
para los casos dudosos: simplemente no se autocorrigen en esta primera
iteración (el párrafo sigue tal cual en ese punto; EST-001 y el LLM de
estilo pueden seguir operando sobre el resto). Los términos del glosario
nunca se tocan.
"""

from __future__ import annotations

from collections.abc import Callable

from ortografia.cliente_languagetool import CoincidenciaLT

FuncionRevisarLT = Callable[[str], list[CoincidenciaLT]]

_CATEGORIA_TYPOS = "TYPOS"


def _es_termino_de_glosario(texto: str, glosario_normalizado: set[str]) -> bool:
    return texto.strip().lower() in glosario_normalizado


def corregir_ortografia_parrafo(
    texto: str, *, glosario: set[str], funcion_revisar_lt: FuncionRevisarLT
) -> str:
    """Reemplaza de atrás hacia adelante (offsets descendentes) para no
    invalidar los índices de las coincidencias restantes."""
    glosario_normalizado = {t.strip().lower() for t in glosario}
    coincidencias = [
        c
        for c in funcion_revisar_lt(texto)
        if c.categoria == _CATEGORIA_TYPOS
        and c.sugerencias
        and not _es_termino_de_glosario(c.texto, glosario_normalizado)
    ]
    for coincidencia in sorted(coincidencias, key=lambda c: c.offset, reverse=True):
        inicio = coincidencia.offset
        fin = inicio + coincidencia.longitud
        texto = texto[:inicio] + coincidencia.sugerencias[0] + texto[fin:]
    return texto
