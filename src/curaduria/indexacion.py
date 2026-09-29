"""Indexación de fragmentos en Qdrant + espejo en Postgres (RF-16, CU-08,
Bloque K3). Construye el payload completo que necesita el filtro/orden de
búsqueda del Bloque K4 (estado, prioridad, fuente_id, version, tipo, area,
seccion, pagina) -- a diferencia de `rag.ingesta.ingerir_fragmentos`
(genérico, payload mínimo: fuente_id/fragmento_id/contenido), acá el
payload es rico a propósito porque el filtrado de K4 debe poder resolverse
sin volver a consultar Postgres por cada resultado.

Solo se indexan fragmentos de una fuente "vigente" (ver
docs/03-diseno/flujos/ingesta-conocimiento.md): el flujo real es aprobar
(`curaduria.fuentes.aprobar_fuente`) primero, indexar después. Cuando esa
misma función obsoletea la versión anterior en Postgres,
`desactivar_fragmentos_de_fuente` hace el equivalente en Qdrant (marca el
payload, no borra los puntos -- conserva el historial de qué se indexó).
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from sqlalchemy.orm import Session

from comun.modelos import Bitacora, Fragmento, FuenteConocimiento
from curaduria.extraccion import FragmentoExtraido, extraer_fragmentos
from rag.ingesta import FuncionEmbedding, asegurar_coleccion

# Debe coincidir con orquestador.pipeline_contable.COLECCION_RAG -- los
# fragmentos de CU-08 conviven con los de CU-01 en la misma colección
# (una sola área piloto, un solo índice de búsqueda semántica).
COLECCION_KB = "kb-contable"


@dataclass(frozen=True)
class ResultadoIndexacion:
    fragmentos_indexados: int
    duracion_segundos: float


def _id_punto(fuente_conocimiento_id: uuid.UUID, indice: int) -> str:
    """Qdrant exige IDs UUID o entero; se deriva uno estable del fragmento
    para que reindexar la misma fuente actualice en vez de duplicar (mismo
    criterio que `rag.ingesta._id_determinista`)."""
    base = f"{fuente_conocimiento_id}:{indice}".encode()
    return str(uuid.UUID(bytes=hashlib.md5(base).digest()))


def indexar_fragmentos(
    sesion: Session,
    cliente_qdrant: QdrantClient,
    *,
    fuente: FuenteConocimiento,
    area_nombre: str,
    fragmentos: list[FragmentoExtraido],
    funcion_embedding: FuncionEmbedding,
    dimension: int,
    coleccion: str = COLECCION_KB,
) -> ResultadoIndexacion:
    """Persiste un `Fragmento` por fragmento extraído y lo indexa en Qdrant
    con el payload completo. `fuente.estado` debe ser "vigente" -- indexar
    contenido de un borrador no tiene sentido (todavía puede cambiar o no
    aprobarse nunca)."""
    if fuente.estado != "vigente":
        raise ValueError(
            f"solo se indexan fuentes 'vigente' (fuente_id={fuente.fuente_id!r} "
            f"está en estado '{fuente.estado}')"
        )

    inicio = time.monotonic()
    asegurar_coleccion(cliente_qdrant, coleccion, dimension)

    puntos: list[qmodels.PointStruct] = []
    for indice, fragmento in enumerate(fragmentos):
        ubicacion = fragmento.seccion
        if ubicacion is None and fragmento.pagina is not None:
            ubicacion = f"Página {fragmento.pagina}"

        fila = Fragmento(
            fuente_id=fuente.id, contenido=fragmento.contenido, pagina_o_seccion=ubicacion
        )
        sesion.add(fila)
        sesion.flush()  # necesita fila.id para el payload del punto

        referencia_vector = _id_punto(fuente.id, indice)
        fila.referencia_vector = referencia_vector

        puntos.append(
            qmodels.PointStruct(
                id=referencia_vector,
                vector=funcion_embedding(fragmento.contenido),
                payload={
                    "fragmento_id": str(fila.id),
                    "fuente_id": fuente.fuente_id,
                    "contenido": fragmento.contenido,
                    "version": fuente.version,
                    "tipo": fuente.tipo,
                    "prioridad": fuente.prioridad,
                    "area": area_nombre,
                    "estado": fuente.estado,
                    "seccion": fragmento.seccion,
                    "pagina": fragmento.pagina,
                },
            )
        )

    if puntos:
        cliente_qdrant.upsert(collection_name=coleccion, points=puntos)
    sesion.flush()

    return ResultadoIndexacion(
        fragmentos_indexados=len(puntos), duracion_segundos=time.monotonic() - inicio
    )


def desactivar_fragmentos_de_fuente(
    cliente_qdrant: QdrantClient, *, coleccion: str, fuente_id_negocio: str
) -> int:
    """Bloque K3: cuando una fuente pasa a "obsoleta" en Postgres (ver
    `curaduria.fuentes.aprobar_fuente`), sus fragmentos ya indexados dejan
    de contar como "vigente" para la búsqueda -- se actualiza el payload en
    vez de borrar los puntos, para no perder el historial de indexación.
    Devuelve cuántos puntos se desactivaron (0 si la fuente nunca se
    indexó o la colección todavía no existe)."""
    if not cliente_qdrant.collection_exists(coleccion):
        return 0

    filtro = qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="fuente_id", match=qmodels.MatchValue(value=fuente_id_negocio)
            )
        ]
    )
    total = cliente_qdrant.count(collection_name=coleccion, count_filter=filtro).count
    if total:
        cliente_qdrant.set_payload(
            collection_name=coleccion, payload={"estado": "obsoleta"}, points=filtro
        )
    return total


def indexar_fuente(
    sesion: Session,
    cliente_qdrant: QdrantClient,
    *,
    fuente: FuenteConocimiento,
    contenido_archivo: bytes,
    tipo_archivo: str,
    area_nombre: str,
    funcion_embedding: FuncionEmbedding,
    dimension: int,
    usuario_id: uuid.UUID,
    coleccion: str = COLECCION_KB,
) -> ResultadoIndexacion:
    """Orquesta el Bloque K3 completo para una fuente recién aprobada:
    extrae (`curaduria.extraccion.extraer_fragmentos`) + indexa
    (`indexar_fragmentos`) + mide y registra el tiempo en la bitácora
    (RF-19) -- el punto de entrada que usará el Bloque K5 al aprobar una
    fuente. Si el PDF no tiene texto, `PdfSinTextoError` se propaga sin
    registrar nada (no hay nada que indexar todavía, `requiere OCR`)."""
    fragmentos = extraer_fragmentos(tipo_archivo, contenido_archivo)
    resultado = indexar_fragmentos(
        sesion,
        cliente_qdrant,
        fuente=fuente,
        area_nombre=area_nombre,
        fragmentos=fragmentos,
        funcion_embedding=funcion_embedding,
        dimension=dimension,
        coleccion=coleccion,
    )
    sesion.add(
        Bitacora(
            usuario_id=usuario_id,
            accion="fuente_indexada",
            entidad_tipo="fuente_conocimiento",
            entidad_id=fuente.id,
            fecha_hora=datetime.now(UTC),
            detalle=(
                f"{resultado.fragmentos_indexados} fragmento(s) indexados en "
                f"{resultado.duracion_segundos:.2f}s (fuente_id={fuente.fuente_id}, "
                f"version={fuente.version})"
            ),
        )
    )
    sesion.commit()
    return resultado
