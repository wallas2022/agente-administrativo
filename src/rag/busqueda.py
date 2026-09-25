"""Búsqueda semántica de fragmentos relevantes (RF-12: fuente citada en cada
hallazgo)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from qdrant_client import QdrantClient

FuncionEmbedding = Callable[[str], list[float]]


@dataclass(frozen=True)
class ResultadoBusqueda:
    fragmento_id: str
    fuente_id: str
    contenido: str
    puntuacion: float


def buscar_fragmentos(
    cliente: QdrantClient,
    *,
    coleccion: str,
    texto_consulta: str,
    funcion_embedding: FuncionEmbedding,
    top_k: int = 3,
) -> list[ResultadoBusqueda]:
    if not cliente.collection_exists(coleccion):
        return []

    vector = funcion_embedding(texto_consulta)
    encontrados = cliente.query_points(
        collection_name=coleccion, query=vector, limit=top_k
    ).points

    return [
        ResultadoBusqueda(
            fragmento_id=(p.payload or {})["fragmento_id"],
            fuente_id=(p.payload or {})["fuente_id"],
            contenido=(p.payload or {})["contenido"],
            puntuacion=p.score,
        )
        for p in encontrados
    ]
