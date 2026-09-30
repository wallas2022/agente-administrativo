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
devuelven (`factor_candidatos`) y se reordenan del lado del cliente.

Bloque K7 (hallazgo de PP-07, docs/04-pruebas/resultados/local-SKB.md): con
una sola consulta, una fuente tipo "referencia" podía no aparecer NUNCA en
un área con >= top_k fuentes regla_interna/normativa, aunque fuera la más
relevante para el hallazgo -- porque competía por los mismos top_k puestos
después de ordenar por prioridad. Ahora "referencia" se busca aparte (su
propia consulta a Qdrant, filtrada a ese tipo, top-1) y solo se agrega si
supera `umbral_referencia` -- no le quita cupo a las reglas ni compite con
ellas."""

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


# 0.5 es un punto de partida razonable para similitud coseno (bge-m3), no
# una cifra medida -- igual que factor_candidatos, queda expuesto como
# parámetro para poder afinarlo con datos reales de un piloto.
UMBRAL_SIMILITUD_REFERENCIA_POR_DEFECTO = 0.5

_TIPOS_REGLA = frozenset({"regla_interna", "normativa"})

_COND_VIGENTE = qmodels.FieldCondition(
    key="estado", match=qmodels.MatchValue(value="vigente")
)
_COND_TIPO_REGLA = qmodels.FieldCondition(
    key="tipo", match=qmodels.MatchAny(any=list(_TIPOS_REGLA))
)

_FILTRO_VIGENTE = qmodels.Filter(must=[_COND_VIGENTE])
# Solo regla_interna/normativa -- lo que puede fundar un hallazgo ("Regla
# aplicada").
_FILTRO_VIGENTE_REGLAS = qmodels.Filter(must=[_COND_VIGENTE, _COND_TIPO_REGLA])
# Todo lo demás: tipo="referencia" explícito, o payload mínimo legado sin
# "tipo" (rag.ingesta.ingerir_fragmentos) -- mismo criterio que el valor
# por defecto que ya usaba ResultadoBusqueda.tipo.
_FILTRO_VIGENTE_REFERENCIA = qmodels.Filter(
    must=[_COND_VIGENTE], must_not=[_COND_TIPO_REGLA]
)


def _a_resultado(punto) -> ResultadoBusqueda:  # noqa: ANN001
    payload = punto.payload or {}
    return ResultadoBusqueda(
        fragmento_id=payload["fragmento_id"],
        fuente_id=payload["fuente_id"],
        contenido=payload["contenido"],
        puntuacion=punto.score,
        prioridad=payload.get("prioridad", 3),
        tipo=payload.get("tipo", "referencia"),
        version=payload.get("version", ""),
        seccion=payload.get("seccion"),
        pagina=payload.get("pagina"),
    )


def buscar_fragmentos(
    cliente: QdrantClient,
    *,
    coleccion: str,
    texto_consulta: str,
    funcion_embedding: FuncionEmbedding,
    top_k: int = 3,
    factor_candidatos: int = 5,
    umbral_referencia: float = UMBRAL_SIMILITUD_REFERENCIA_POR_DEFECTO,
) -> list[ResultadoBusqueda]:
    if not cliente.collection_exists(coleccion):
        return []

    vector = funcion_embedding(texto_consulta)

    encontrados_reglas = cliente.query_points(
        collection_name=coleccion,
        query=vector,
        query_filter=_FILTRO_VIGENTE_REGLAS,
        limit=max(top_k * factor_candidatos, top_k),
    ).points
    candidatos = [_a_resultado(p) for p in encontrados_reglas]
    candidatos.sort(key=lambda r: (r.prioridad, -r.puntuacion))
    resultado = candidatos[:top_k]

    encontrados_referencia = cliente.query_points(
        collection_name=coleccion,
        query=vector,
        query_filter=_FILTRO_VIGENTE_REFERENCIA,
        limit=1,
    ).points
    if encontrados_referencia and encontrados_referencia[0].score >= umbral_referencia:
        resultado.append(_a_resultado(encontrados_referencia[0]))

    return resultado


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
