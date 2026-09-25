"""Tarea de Celery: consume la cola y transiciona el estado del documento/análisis.

Sin lógica de negocio real todavía (sin validadores): esta es la orquestación
de estados de F1/L2 (docs/03-diseno/estados/estados-analisis.md); los
adaptadores por tipo de revisión se agregan en Sprint 1 (CU-01).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from comun.cola import app
from comun.db import obtener_fabrica_sesion
from comun.estados import EstadoAnalisis, EstadoDocumento
from comun.modelos import Analisis, Bitacora, Documento


def _registrar_bitacora(
    sesion: Session, *, usuario_id: uuid.UUID, accion: str, entidad_id: uuid.UUID
) -> None:
    sesion.add(
        Bitacora(
            usuario_id=usuario_id,
            accion=accion,
            entidad_tipo="analisis",
            entidad_id=entidad_id,
            fecha_hora=datetime.now(UTC),
        )
    )


def ejecutar_analisis(sesion: Session, documento_id: uuid.UUID, analisis_id: uuid.UUID) -> str:
    """Lógica pura (sin Celery) para poder probarla con una sesión en memoria."""
    documento = sesion.get(Documento, documento_id)
    analisis = sesion.get(Analisis, analisis_id)
    if documento is None or analisis is None:
        return EstadoDocumento.FALLIDO.value

    documento.estado = EstadoDocumento.PROCESANDO.value
    _registrar_bitacora(
        sesion, usuario_id=analisis.usuario_id, accion="analisis_iniciado", entidad_id=analisis.id
    )
    sesion.commit()

    # Sin validadores todavía (Sprint 1): todo análisis pasa a revisión sin
    # hallazgos, tal como documenta el flujo alterno de CU-01 (ver
    # docs/03-diseno/secuencia/cu-01-excel-contable.md).
    documento.estado = EstadoDocumento.EN_REVISION.value
    analisis.estado = EstadoAnalisis.COMPLETADO.value
    analisis.fecha_fin = datetime.now(UTC)
    _registrar_bitacora(
        sesion,
        usuario_id=analisis.usuario_id,
        accion="analisis_completado",
        entidad_id=analisis.id,
    )
    sesion.commit()
    return documento.estado


@app.task(name="orquestador.tareas.analizar_documento")
def analizar_documento(documento_id: str, analisis_id: str) -> str:
    sesion = obtener_fabrica_sesion()()
    try:
        return ejecutar_analisis(sesion, uuid.UUID(documento_id), uuid.UUID(analisis_id))
    finally:
        sesion.close()
