"""Aprobación asíncrona de una fuente de conocimiento (P-15, ADR-010).

Aprobar ya no indexa dentro de la petición HTTP: `iniciar_indexacion` deja la
fuente en "indexando" y un worker corre `procesar_indexacion`, que al terminar
la deja "vigente" (la versión anterior pasa a "obsoleta" en la misma
transacción de Postgres) o en "error_indexacion" con el motivo, para
reintentarla. Mientras indexa, la versión anterior sigue vigente y buscable.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from sqlalchemy.orm import Session

from comun.almacenamiento import ObjetoNoEncontradoError
from comun.modelos import Area, Bitacora, Fragmento, FuenteConocimiento
from curaduria.extraccion import PdfSinTextoError, extraer_fragmentos
from curaduria.fuentes import aprobar_fuente
from curaduria.indexacion import indexar_fragmentos
from rag.ingesta import FuncionEmbedding

ESTADOS_INICIABLES = ("borrador", "error_indexacion")
_MAX_MOTIVO = 500
_MENSAJE_OBJETO_AUSENTE = "El archivo de la fuente no está en el almacenamiento; súbalo de nuevo"
_MENSAJE_MODELOS_LENTOS = (
    "El servicio de embeddings tardó demasiado en responder; reintente en unos minutos"
)


@dataclass(frozen=True)
class ResultadoProcesamiento:
    estado: str
    fragmentos_indexados: int = 0
    version_anterior_obsoleta: bool = False
    duracion_segundos: float = 0.0
    motivo: str | None = None


def _bitacora(
    sesion: Session, *, usuario_id: uuid.UUID, accion: str, fuente: FuenteConocimiento, detalle: str
) -> None:
    sesion.add(
        Bitacora(
            usuario_id=usuario_id,
            accion=accion,
            entidad_tipo="fuente_conocimiento",
            entidad_id=fuente.id,
            fecha_hora=datetime.now(UTC),
            detalle=detalle,
        )
    )


def iniciar_indexacion(
    sesion: Session, fuente: FuenteConocimiento, *, usuario_id: uuid.UUID
) -> None:
    """borrador | error_indexacion -> indexando. No hace commit: el llamador
    confirma la transición antes de encolar la tarea."""
    if fuente.estado not in ESTADOS_INICIABLES:
        raise ValueError(
            f"La fuente está en estado '{fuente.estado}'; solo se aprueba desde 'borrador' "
            "o se reintenta desde 'error_indexacion'"
        )
    reintento = fuente.estado == "error_indexacion"
    fuente.estado = "indexando"
    fuente.motivo_error = None
    fuente.fragmentos_total = None
    fuente.fragmentos_procesados = None
    _bitacora(
        sesion,
        usuario_id=usuario_id,
        accion="fuente_indexacion_reintentada" if reintento else "fuente_indexacion_iniciada",
        fuente=fuente,
        detalle=f"{fuente.fuente_id} v{fuente.version} -> indexando",
    )
    sesion.flush()


def _motivo_legible(error: Exception) -> str:
    if isinstance(error, ObjetoNoEncontradoError):
        return _MENSAJE_OBJETO_AUSENTE
    if isinstance(error, httpx.TimeoutException):
        return _MENSAJE_MODELOS_LENTOS
    if isinstance(error, PdfSinTextoError):
        return str(error)
    return f"{type(error).__name__}: {error}"[:_MAX_MOTIVO]


def _borrar_intento_previo(
    sesion: Session, cliente_qdrant: QdrantClient, coleccion: str, fuente: FuenteConocimiento
) -> None:
    """Quita fragmentos y puntos de un intento anterior (reintento idempotente)."""
    filas = sesion.query(Fragmento).filter_by(fuente_id=fuente.id).all()
    ids: list[int | str] = [f.referencia_vector for f in filas if f.referencia_vector]
    if ids and cliente_qdrant.collection_exists(coleccion):
        cliente_qdrant.delete(
            collection_name=coleccion,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(must=[qmodels.HasIdCondition(has_id=ids)])
            ),
        )
    sesion.query(Fragmento).filter_by(fuente_id=fuente.id).delete()
    sesion.flush()


def _registrar_fallo(
    sesion: Session,
    cliente_qdrant: QdrantClient,
    coleccion: str,
    fuente_id: uuid.UUID,
    usuario_id: uuid.UUID,
    error: Exception,
) -> ResultadoProcesamiento:
    sesion.rollback()
    fuente = sesion.get(FuenteConocimiento, fuente_id)
    assert fuente is not None
    motivo = _motivo_legible(error)
    try:
        _borrar_intento_previo(sesion, cliente_qdrant, coleccion, fuente)
    except Exception:  # noqa: BLE001 - la limpieza no debe ocultar el error original
        sesion.rollback()
        fuente = sesion.get(FuenteConocimiento, fuente_id)
        assert fuente is not None
    fuente.estado = "error_indexacion"
    fuente.motivo_error = motivo
    _bitacora(
        sesion,
        usuario_id=usuario_id,
        accion="fuente_indexacion_fallida",
        fuente=fuente,
        detalle=f"{fuente.fuente_id} v{fuente.version} -> error_indexacion: {motivo}",
    )
    sesion.commit()
    return ResultadoProcesamiento(estado="error_indexacion", motivo=motivo)


def procesar_indexacion(
    sesion: Session,
    cliente_qdrant: QdrantClient,
    *,
    fuente_id: uuid.UUID,
    usuario_id: uuid.UUID,
    obtener_contenido: Callable[[], bytes],
    funcion_embedding: FuncionEmbedding,
    dimension: int,
    coleccion: str,
) -> ResultadoProcesamiento:
    """Extrae, embebe e indexa la fuente (en "indexando") y la deja vigente.
    Nunca lanza por fallas de indexación: las registra como "error_indexacion"."""
    fuente = sesion.get(FuenteConocimiento, fuente_id)
    if fuente is None:
        return ResultadoProcesamiento(estado="inexistente", motivo="Fuente no encontrada")
    if fuente.estado != "indexando":
        # Entrega duplicada de la tarea: otro worker ya la resolvió.
        return ResultadoProcesamiento(estado=fuente.estado)

    inicio = time.monotonic()
    try:
        contenido = obtener_contenido()
        extension = fuente.archivo.rsplit(".", 1)[-1] if "." in fuente.archivo else ""
        fragmentos = extraer_fragmentos(extension, contenido)
        _borrar_intento_previo(sesion, cliente_qdrant, coleccion, fuente)
        fuente.fragmentos_total = len(fragmentos)
        fuente.fragmentos_procesados = 0
        sesion.commit()

        def _progreso(procesados: int, _total: int) -> None:
            fuente.fragmentos_procesados = procesados
            sesion.commit()

        area = sesion.get(Area, fuente.area_id)
        indexar_fragmentos(
            sesion,
            cliente_qdrant,
            fuente=fuente,
            area_nombre=area.nombre if area else "",
            fragmentos=fragmentos,
            funcion_embedding=funcion_embedding,
            dimension=dimension,
            coleccion=coleccion,
            estado_payload="indexando",
            exigir_vigente=False,
            al_progresar=_progreso,
        )

        ids: list[int | str] = [
            f.referencia_vector
            for f in sesion.query(Fragmento).filter_by(fuente_id=fuente.id).all()
            if f.referencia_vector
        ]
        anterior = aprobar_fuente(sesion, fuente, aprobado_por=usuario_id, ahora=datetime.now(UTC))
        # Primero se activa lo nuevo y después se apaga lo viejo: si algo falla
        # entre ambos pasos quedan dos versiones buscables un momento, nunca ninguna.
        if ids:
            cliente_qdrant.set_payload(
                collection_name=coleccion,
                payload={"estado": "vigente"},
                points=ids,
            )
        if anterior is not None:
            cliente_qdrant.set_payload(
                collection_name=coleccion,
                payload={"estado": "obsoleta"},
                points=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="fuente_id", match=qmodels.MatchValue(value=fuente.fuente_id)
                        )
                    ],
                    must_not=[qmodels.HasIdCondition(has_id=ids)],
                ),
            )
        duracion = time.monotonic() - inicio
        fuente.motivo_error = None
        _bitacora(
            sesion,
            usuario_id=usuario_id,
            accion="fuente_aprobada",
            fuente=fuente,
            detalle=f"{fuente.fuente_id} v{fuente.version} -> vigente",
        )
        _bitacora(
            sesion,
            usuario_id=usuario_id,
            accion="fuente_indexada",
            fuente=fuente,
            detalle=(
                f"{len(ids)} fragmento(s) indexados en {duracion:.2f}s "
                f"(fuente_id={fuente.fuente_id}, version={fuente.version})"
            ),
        )
        sesion.commit()
        return ResultadoProcesamiento(
            estado="vigente",
            fragmentos_indexados=len(ids),
            version_anterior_obsoleta=anterior is not None,
            duracion_segundos=duracion,
        )
    except Exception as error:  # noqa: BLE001 - toda falla se registra en la fuente
        return _registrar_fallo(sesion, cliente_qdrant, coleccion, fuente_id, usuario_id, error)
