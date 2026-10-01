"""Corrección ortográfica determinista por párrafo (CU-02, fase 2): reutiliza
LanguageTool + el glosario interno de CU-05 (`ortografia.cliente_languagetool`,
`comun.glosario`) antes de pasar el párrafo a las reglas EST-001 y al LLM.

Solo se aplican automáticamente las coincidencias de la familia de reglas
"ES_SIMPLE_REPLACE_*" (categoría "TYPOS") -- un diccionario curado de
reemplazos 1 a 1 inequívocos ("dia" -> "día", "aqui" -> "aquí"), siempre de
una sola palabra. Encontrado probando con texto real: la categoría "TYPOS"
por sí sola NO alcanza como filtro -- también incluye "MORFOLOGIK_RULE_ES"
(el corrector ortográfico general contra el diccionario), que para "se
aprobo" propone como primera sugerencia "sea probo" (sin sentido) y para una
sigla no reconocida como "DAF" propone "DA" (le corta una letra). Aplicar a
ciegas la primera sugerencia de una regla tan amplia corrompe el texto en
vez de corregirlo. A diferencia de `ortografia.revision` (CU-05), acá no hay
un paso de confirmación por LLM para los casos dudosos: lo que no cae en
ES_SIMPLE_REPLACE_* simplemente no se autocorrige en esta primera iteración
(el párrafo sigue tal cual en ese punto; EST-001 y el LLM de estilo pueden
seguir operando sobre el resto). Los términos del glosario nunca se tocan.
"""

from __future__ import annotations

from collections.abc import Callable

from ortografia.cliente_languagetool import CoincidenciaLT

FuncionRevisarLT = Callable[[str], list[CoincidenciaLT]]

_CATEGORIA_TYPOS = "TYPOS"
_PREFIJO_REGLA_SEGURA = "ES_SIMPLE_REPLACE"


def _es_termino_de_glosario(texto: str, glosario_normalizado: set[str]) -> bool:
    return texto.strip().lower() in glosario_normalizado


def _es_correccion_segura(coincidencia: CoincidenciaLT) -> bool:
    return (
        coincidencia.categoria == _CATEGORIA_TYPOS
        and coincidencia.regla_id.startswith(_PREFIJO_REGLA_SEGURA)
        and bool(coincidencia.sugerencias)
        and " " not in coincidencia.texto.strip()  # nunca reemplazar un tramo de varias palabras
    )


def corregir_ortografia_parrafo(
    texto: str, *, glosario: set[str], funcion_revisar_lt: FuncionRevisarLT
) -> str:
    """Reemplaza de atrás hacia adelante (offsets descendentes) para no
    invalidar los índices de las coincidencias restantes."""
    glosario_normalizado = {t.strip().lower() for t in glosario}
    coincidencias = [
        c
        for c in funcion_revisar_lt(texto)
        if _es_correccion_segura(c) and not _es_termino_de_glosario(c.texto, glosario_normalizado)
    ]
    for coincidencia in sorted(coincidencias, key=lambda c: c.offset, reverse=True):
        inicio = coincidencia.offset
        fin = inicio + coincidencia.longitud
        texto = texto[:inicio] + coincidencia.sugerencias[0] + texto[fin:]
    return texto
