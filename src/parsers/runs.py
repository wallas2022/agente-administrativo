"""Reemplazo de texto dentro de un párrafo preservando el formato de cada
`run` existente (RF-14) -- compartido entre docx y pptx porque ambos
exponen la misma forma: un párrafo con una lista de `runs`, cada uno con
`.text` de solo texto plano y su propio formato (negrita, etc.) que no debe
perderse al corregir.
"""

from __future__ import annotations

from typing import Any


def reemplazar_texto_en_parrafo(parrafo: Any, texto_original: str, texto_nuevo: str) -> bool:
    """Busca `texto_original` en el texto concatenado de todas las corridas
    del párrafo y lo reemplaza por `texto_nuevo`, recortando/vaciando solo
    las corridas que se solapan con el rango encontrado. El texto nuevo
    completo se inserta en la primera corrida que toca el rango, con SU
    formato -- las demás corridas tocadas por el rango se recortan a lo que
    quede antes/después, sin duplicar el texto nuevo.

    Devuelve False (sin tocar el párrafo) si `texto_original` no aparece.
    Solo reemplaza la primera aparición -- suficiente en la práctica porque
    `ubicacion` (párrafo/celda/viñeta) ya es lo bastante granular para que
    el mismo texto exacto rara vez se repita dos veces ahí.
    """
    corridas = list(parrafo.runs)
    texto_completo = "".join(c.text for c in corridas)
    inicio = texto_completo.find(texto_original)
    if inicio == -1:
        return False
    fin = inicio + len(texto_original)

    posicion = 0
    ya_inserto_reemplazo = False
    for corrida in corridas:
        inicio_corrida = posicion
        fin_corrida = posicion + len(corrida.text)
        posicion = fin_corrida

        if fin_corrida <= inicio or inicio_corrida >= fin:
            continue  # esta corrida no se solapa con el rango a reemplazar

        prefijo = corrida.text[: max(0, inicio - inicio_corrida)]
        sufijo = corrida.text[max(0, fin - inicio_corrida) :]

        if not ya_inserto_reemplazo:
            corrida.text = prefijo + texto_nuevo + sufijo
            ya_inserto_reemplazo = True
        else:
            corrida.text = prefijo + sufijo

    return True
