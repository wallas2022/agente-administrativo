"""Generación del documento corregido (RF-14, CU-05, Bloque O4).

A diferencia de CU-01, esto NO corre dentro del pipeline del worker: según
el diseño (docs/03-diseno/secuencia/cu-05-ortografia.md, supuesto 4), el
documento corregido se genera solo después de que el Revisor decide sobre
los hallazgos (CU-07). Vive en `ortografia/` (no en `orquestador/`) para que
tanto la API (que lo invoca bajo demanda, síncronamente -- no hay LLM de por
medio, solo aplicar texto ya decidido) como el worker puedan importarlo sin
que uno dependa del paquete completo del otro.
"""

from __future__ import annotations

import io

from comun.modelos import Hallazgo
from parsers.correcciones import CorreccionAplicable
from parsers.docx import aplicar_correcciones_docx, construir_docx_desde_segmentos
from parsers.pdf import leer_texto_pdf
from parsers.pptx import aplicar_correcciones_pptx
from parsers.texto_plano import aplicar_correcciones_texto_plano
from parsers.xlsx import aplicar_correcciones_xlsx


def _correcciones_desde_hallazgos_aceptados(
    hallazgos: list[Hallazgo],
) -> list[CorreccionAplicable]:
    return [
        CorreccionAplicable(
            ubicacion=h.ubicacion,
            texto_original=h.texto_original,
            texto_nuevo=h.correccion_sugerida,
        )
        for h in hallazgos
        if h.estado == "aceptado" and h.texto_original and h.correccion_sugerida
    ]


def generar_documento_corregido(
    *, tipo_archivo: str, contenido_original: bytes, hallazgos: list[Hallazgo]
) -> tuple[bytes, str] | None:
    """RF-14: aplica solo las correcciones ACEPTADAS (CU-07) sobre el
    documento original. Devuelve `(contenido, extension)` -- la extensión
    puede cambiar (PDF -> docx, RF-14: "no se reescribe el PDF") -- o None
    si no hay ninguna corrección aceptada (no tiene sentido generar una
    copia idéntica al original)."""
    correcciones = _correcciones_desde_hallazgos_aceptados(hallazgos)
    if not correcciones:
        return None

    extension = tipo_archivo.lower().lstrip(".")
    if extension == "docx":
        resultado = aplicar_correcciones_docx(io.BytesIO(contenido_original), correcciones)
        return resultado.contenido, "docx"
    if extension == "pptx":
        resultado = aplicar_correcciones_pptx(io.BytesIO(contenido_original), correcciones)
        return resultado.contenido, "pptx"
    if extension == "xlsx":
        resultado = aplicar_correcciones_xlsx(io.BytesIO(contenido_original), correcciones)
        return resultado.contenido, "xlsx"
    if extension == "txt":
        texto = contenido_original.decode("utf-8", errors="replace")
        return aplicar_correcciones_texto_plano(texto, correcciones).encode("utf-8"), "txt"
    if extension == "pdf":
        segmentos = leer_texto_pdf(io.BytesIO(contenido_original))
        return construir_docx_desde_segmentos(segmentos, correcciones), "docx"
    raise ValueError(f"Formato no soportado para generar documento corregido: {tipo_archivo!r}")
