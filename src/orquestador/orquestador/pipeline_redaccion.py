"""Pipeline de CU-02 (RF-07, RF-12): conecta extracción (`parsers`) → reglas
deterministas de redacción (RD-01 a RD-04, `validadores.redaccion.reglas`)
→ persistencia. Lo invoca `tareas.ejecutar_analisis` cuando
`tipo_revision == "redaccion"`.

Mismo criterio de dos fases que CU-05 (Bloque O6): esta es la fase 1 --
solo reglas deterministas, sin LLM, rápida, visible de inmediato. La fase 2
(LLM por párrafo con streaming) NO corre acá -- el frontend la dispara
aparte contra `GET /analisis/{id}/mejorar-stream` apenas aterriza en la
pantalla de resultados (ver `api/main.py` y
docs/02-analisis/02-analisis-cu02-redaccion-amigable.md §2.1).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from comun.modelos import Analisis, Hallazgo, VersionDocumento
from parsers.segmentos import SegmentoTexto
from validadores.redaccion.extraccion import FORMATOS_SOPORTADOS, extraer_parrafos
from validadores.redaccion.reglas import validar_redaccion

__all__ = ["FORMATOS_SOPORTADOS", "extraer_parrafos", "procesar_documento_redaccion"]


def procesar_documento_redaccion(
    sesion: Session,
    *,
    analisis: Analisis,
    version_original: VersionDocumento,
    contenido_original: bytes,
    tipo_archivo: str,
    tipo_documento: str,
) -> tuple[list[Hallazgo], list[SegmentoTexto]]:
    """Fase 1: reglas deterministas EST-001 (RD-01 a RD-04), sin LLM.
    Devuelve también los párrafos extraídos para que la fase 2 (SSE) no
    tenga que descargar y re-extraer el documento original."""
    parrafos = extraer_parrafos(tipo_archivo, contenido_original)
    hallazgos_deterministas = validar_redaccion(parrafos, tipo_documento=tipo_documento)

    filas: list[Hallazgo] = []
    for h in hallazgos_deterministas:
        fila = Hallazgo(
            analisis_id=analisis.id,
            version_documento_id=version_original.id,
            severidad=h.severidad,
            ubicacion=h.ubicacion,
            descripcion=h.descripcion,
            estado="pendiente",
            fuente_citada=(
                f"Regla aplicada: EST-001 {h.cita_est001}" if h.cita_est001 else None
            ),
        )
        sesion.add(fila)
        filas.append(fila)

    sesion.flush()
    return filas, parrafos
