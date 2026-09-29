"""Búsqueda semántica de fragmentos relevantes (RF-12: fuente citada en cada
hallazgo).

Bloque K4 (RF-16, CU-08): solo se buscan fragmentos de fuentes "vigente"
(filtro por payload, ver `curaduria.indexacion` -- los fragmentos de
fuentes obsoletas quedan con `estado="obsoleta"` en su payload y no
pueden ganar ni por prioridad ni por similitud) y se ordena primero por
`prioridad` (1=regla_interna, 2=normativa, 3=referencia) y solo entre
resultados de la misma prioridad, por similitud semántica -- una regla
interna con puntuación algo menor sigue pesando más que una referencia con
puntuación más alta. Para eso se piden más candidatos de los que se
devuelven (`factor_candidatos`) y se reordenan del lado del cliente."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

FuncionEmbedding = Callable[[str], list[float]]


@dataclass(frozen=True)
class ResultadoBusqueda:
    fragmento_id: str
    fuente_id: str
    contenido: str
    puntuacion: float
    prioridad: int
    tipo: str
    version: str
    seccion: str | None
    pagina: int | None


_FILTRO_VIGENTE = qmodels.Filter(
    must=[qmodels.FieldCondition(key="estado", match=qmodels.MatchValue(value="vigente"))]
)


def buscar_fragmentos(
    cliente: QdrantClient,
    *,
    coleccion: str,
    texto_consulta: str,
    funcion_embedding: FuncionEmbedding,
    top_k: int = 3,
    factor_candidatos: int = 5,
) -> list[ResultadoBusqueda]:
    if not cliente.collection_exists(coleccion):
        return []

    vector = funcion_embedding(texto_consulta)
    encontrados = cliente.query_points(
        collection_name=coleccion,
        query=vector,
        query_filter=_FILTRO_VIGENTE,
        limit=max(top_k * factor_candidatos, top_k),
    ).points

    candidatos = [
        ResultadoBusqueda(
            fragmento_id=(p.payload or {})["fragmento_id"],
            fuente_id=(p.payload or {})["fuente_id"],
            contenido=(p.payload or {})["contenido"],
            puntuacion=p.score,
            # Payload mínimo (rag.ingesta.ingerir_fragmentos, CU-01 legado)
            # vs. payload completo (curaduria.indexacion, Bloque K3): si no
            # hay prioridad/tipo/version, se asume la prioridad más baja
            # (referencia) para no ganarle a un resultado sí clasificado.
            prioridad=(p.payload or {}).get("prioridad", 3),
            tipo=(p.payload or {}).get("tipo", "referencia"),
            version=(p.payload or {}).get("version", ""),
            seccion=(p.payload or {}).get("seccion"),
            pagina=(p.payload or {}).get("pagina"),
        )
        for p in encontrados
    ]
    candidatos.sort(key=lambda r: (r.prioridad, -r.puntuacion))
    return candidatos[:top_k]


# tipo="referencia" (prioridad 3) nunca funda un hallazgo -- solo
# regla_interna/normativa pueden ser la "Regla aplicada".
_TIPOS_FUNDAMENTO = frozenset({"regla_interna", "normativa"})


def _formatear_regla_aplicada(fragmento: ResultadoBusqueda) -> str:
    cita = f" {fragmento.seccion}" if fragmento.seccion else ""
    return f"Regla aplicada: {fragmento.fuente_id}{cita} (v{fragmento.version})"


def _formatear_referencia(fragmento: ResultadoBusqueda) -> str:
    detalle = ""
    if fragmento.seccion:
        detalle = f", cap. {fragmento.seccion}"
    elif fragmento.pagina is not None:
        detalle = f", pág. {fragmento.pagina}"
    return f"Referencia: {fragmento.fuente_id}{detalle}"


def construir_citas(fragmentos: list[ResultadoBusqueda]) -> tuple[str | None, str | None]:
    """Bloque K4: separa el fragmento que funda el hallazgo ("Regla
    aplicada: POL-001 §3 (v2026-01)") del que solo lo complementa
    ("Referencia: <fuente> cap./pág."). `fragmentos` debe venir ya
    ordenado por prioridad/similitud (ver `buscar_fragmentos`): se toma el
    primer resultado de cada categoría. Un fragmento tipo="referencia"
    JAMÁS se usa como fundamento -- si no hay ningún regla_interna/
    normativa entre los resultados, no hay "Regla aplicada" (queda en
    `None`), aunque sí pueda haber "Referencia"."""
    regla_aplicada: str | None = None
    referencia: str | None = None
    for fragmento in fragmentos:
        if regla_aplicada is None and fragmento.tipo in _TIPOS_FUNDAMENTO:
            regla_aplicada = _formatear_regla_aplicada(fragmento)
        elif referencia is None and fragmento.tipo == "referencia":
            referencia = _formatear_referencia(fragmento)
        if regla_aplicada is not None and referencia is not None:
            break
    return regla_aplicada, referencia
