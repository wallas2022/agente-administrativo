"""Ingesta de fragmentos de la base de conocimiento en Qdrant (RF-16, CU-08).

Sin lógica de negocio de validación: solo fragmenta, calcula embeddings (vía
`funcion_embedding`, inyectable para pruebas) y hace upsert en la colección.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

FuncionEmbedding = Callable[[str], list[float]]


def _id_determinista(fuente_id: str, fragmento_id: str) -> str:
    """Qdrant exige IDs UUID o entero; se deriva un UUID estable del
    fragmento para que reingerir la misma fuente actualice en vez de duplicar.
    """
    base = f"{fuente_id}:{fragmento_id}".encode()
    return str(uuid.UUID(bytes=hashlib.md5(base).digest()))


def asegurar_coleccion(cliente: QdrantClient, coleccion: str, dimension: int) -> None:
    if not cliente.collection_exists(coleccion):
        cliente.create_collection(
            collection_name=coleccion,
            vectors_config=qmodels.VectorParams(size=dimension, distance=qmodels.Distance.COSINE),
        )


def ingerir_fragmentos(
    cliente: QdrantClient,
    *,
    coleccion: str,
    fuente_id: str,
    fragmentos: list[tuple[str, str]],  # (fragmento_id, contenido)
    funcion_embedding: FuncionEmbedding,
    dimension: int,
) -> int:
    asegurar_coleccion(cliente, coleccion, dimension)

    puntos = [
        qmodels.PointStruct(
            id=_id_determinista(fuente_id, fragmento_id),
            vector=funcion_embedding(contenido),
            payload={"fuente_id": fuente_id, "fragmento_id": fragmento_id, "contenido": contenido},
        )
        for fragmento_id, contenido in fragmentos
    ]
    if not puntos:
        return 0
    cliente.upsert(collection_name=coleccion, points=puntos)
    return len(puntos)
