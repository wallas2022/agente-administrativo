import uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from rag.busqueda import ResultadoBusqueda, buscar_fragmentos, construir_citas
from rag.ingesta import asegurar_coleccion, ingerir_fragmentos

COLECCION = "agente_admin_kb_prueba"
DIMENSION = 8


def _embedding_falso(texto: str) -> list[float]:
    """Vector determinista y simple: más parecido cuanto más se repite una
    palabra clave, suficiente para probar la mecánica de ingesta/búsqueda sin
    depender de bge-m3 real."""
    claves = ["cuadre", "catalogo", "periodo", "duplicado", "moneda", "formula", "cierre", "otro"]
    texto_normalizado = texto.lower()
    return [float(texto_normalizado.count(clave)) for clave in claves] or [0.0] * DIMENSION


def _cliente_en_memoria() -> QdrantClient:
    cliente = QdrantClient(":memory:")
    return cliente


def test_ingerir_y_buscar_devuelve_el_fragmento_mas_relevante() -> None:
    cliente = _cliente_en_memoria()
    fragmentos = [
        ("f1", "El cuadre de partidas exige que debe y haber sean iguales."),
        ("f2", "El catalogo de cuentas define qué cuentas son validas."),
        ("f3", "La mezcla de moneda Q y USD requiere tipo de cambio."),
    ]

    ingerir_fragmentos(
        cliente,
        coleccion=COLECCION,
        fuente_id="politica-cierre-contable",
        fragmentos=fragmentos,
        funcion_embedding=_embedding_falso,
        dimension=DIMENSION,
    )

    resultados = buscar_fragmentos(
        cliente,
        coleccion=COLECCION,
        texto_consulta="hay un descuadre entre el debe y el haber",
        funcion_embedding=_embedding_falso,
        top_k=1,
    )

    assert len(resultados) == 1
    assert resultados[0].fragmento_id == "f1"
    assert resultados[0].fuente_id == "politica-cierre-contable"
    assert resultados[0].puntuacion > 0


def test_buscar_sin_fragmentos_ingeridos_devuelve_lista_vacia() -> None:
    cliente = _cliente_en_memoria()

    resultados = buscar_fragmentos(
        cliente,
        coleccion="coleccion-vacia",
        texto_consulta="algo",
        funcion_embedding=_embedding_falso,
        top_k=3,
    )

    assert resultados == []


# --- Bloque K4: filtro estado=vigente y orden por prioridad -----------------


def _insertar_punto(
    cliente: QdrantClient,
    *,
    coleccion: str,
    id_punto: str,
    vector: list[float],
    fuente_id: str,
    contenido: str,
    estado: str = "vigente",
    prioridad: int = 1,
    tipo: str = "regla_interna",
    version: str = "1.0",
    seccion: str | None = None,
    pagina: int | None = None,
) -> None:
    asegurar_coleccion(cliente, coleccion, DIMENSION)
    cliente.upsert(
        collection_name=coleccion,
        points=[
            qmodels.PointStruct(
                # Qdrant exige que el id del punto sea UUID o entero -- el
                # identificador legible va en el payload (fragmento_id, lo
                # que de verdad lee ResultadoBusqueda).
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, id_punto)),
                vector=vector,
                payload={
                    "fragmento_id": id_punto,
                    "fuente_id": fuente_id,
                    "contenido": contenido,
                    "estado": estado,
                    "prioridad": prioridad,
                    "tipo": tipo,
                    "version": version,
                    "seccion": seccion,
                    "pagina": pagina,
                },
            )
        ],
    )


def test_buscar_fragmentos_excluye_fuentes_obsoletas() -> None:
    cliente = _cliente_en_memoria()
    _insertar_punto(
        cliente, coleccion=COLECCION, id_punto="v", vector=_embedding_falso("cuadre"),
        fuente_id="POL-001", contenido="Fragmento vigente sobre cuadre.", estado="vigente",
    )
    _insertar_punto(
        cliente, coleccion=COLECCION, id_punto="o", vector=_embedding_falso("cuadre"),
        fuente_id="POL-000", contenido="Fragmento obsoleto sobre cuadre.", estado="obsoleta",
    )

    resultados = buscar_fragmentos(
        cliente, coleccion=COLECCION, texto_consulta="descuadre",
        funcion_embedding=_embedding_falso, top_k=5,
    )

    assert {r.fragmento_id for r in resultados} == {"v"}


def test_buscar_fragmentos_ordena_por_prioridad_antes_que_por_similitud() -> None:
    """Una fuente de prioridad 1 (regla_interna) le gana a una de prioridad 3
    (referencia) aunque esta última tenga mejor puntuación de similitud."""
    cliente = _cliente_en_memoria()
    vector_consulta = _embedding_falso("cuadre")
    _insertar_punto(
        cliente, coleccion=COLECCION, id_punto="referencia", vector=vector_consulta,
        fuente_id="REF-001", contenido="El cuadre de partidas exige que debe y haber sean iguales.",
        prioridad=3, tipo="referencia",
    )
    _insertar_punto(
        cliente, coleccion=COLECCION, id_punto="regla",
        vector=_embedding_falso("un vector distinto, menos parecido"),
        fuente_id="POL-001", contenido="Cuadre de partidas: ver política interna.",
        prioridad=1, tipo="regla_interna", seccion="§3",
    )

    resultados = buscar_fragmentos(
        cliente, coleccion=COLECCION, texto_consulta="cuadre", funcion_embedding=_embedding_falso,
        top_k=2,
    )

    assert [r.fragmento_id for r in resultados] == ["regla", "referencia"]
    assert resultados[0].prioridad == 1
    assert resultados[0].seccion == "§3"


def test_buscar_fragmentos_con_payload_minimo_legado_asume_prioridad_baja() -> None:
    """rag.ingesta.ingerir_fragmentos (payload mínimo, sin prioridad/tipo) no
    debe ganarle por accidente a un resultado del Bloque K3 sí clasificado."""
    cliente = _cliente_en_memoria()
    ingerir_fragmentos(
        cliente, coleccion=COLECCION, fuente_id="politica-cierre-contable",
        fragmentos=[("legado", "El cuadre de partidas exige que debe y haber sean iguales.")],
        funcion_embedding=_embedding_falso, dimension=DIMENSION,
    )
    _insertar_punto(
        cliente, coleccion=COLECCION, id_punto="k3",
        vector=_embedding_falso("un vector distinto"),
        fuente_id="POL-001", contenido="Cuadre de partidas: ver política interna.",
        prioridad=1, tipo="regla_interna",
    )

    resultados = buscar_fragmentos(
        cliente, coleccion=COLECCION, texto_consulta="cuadre", funcion_embedding=_embedding_falso,
        top_k=2,
    )

    assert resultados[0].fragmento_id == "k3"
    assert next(r for r in resultados if r.fragmento_id == "legado").prioridad == 3


# --- Bloque K4: construir_citas ("Regla aplicada" vs. "Referencia") ---------


def _resultado(
    *, tipo: str, fuente_id: str = "POL-001", seccion: str | None = "§3",
    version: str = "2026-01", pagina: int | None = None, prioridad: int = 1,
) -> ResultadoBusqueda:
    return ResultadoBusqueda(
        fragmento_id="f", fuente_id=fuente_id, contenido="...", puntuacion=0.9,
        prioridad=prioridad, tipo=tipo, version=version, seccion=seccion, pagina=pagina,
    )


def test_construir_citas_regla_interna_es_regla_aplicada() -> None:
    regla_aplicada, referencia = construir_citas([_resultado(tipo="regla_interna")])

    assert regla_aplicada == "Regla aplicada: POL-001 §3 (v2026-01)"
    assert referencia is None


def test_construir_citas_normativa_tambien_es_regla_aplicada() -> None:
    regla_aplicada, _referencia = construir_citas([_resultado(tipo="normativa")])

    assert regla_aplicada is not None
    assert regla_aplicada.startswith("Regla aplicada:")


def test_construir_citas_referencia_nunca_es_regla_aplicada() -> None:
    """Aunque sea el único resultado y el de mejor puntuación, una
    "referencia" no funda el hallazgo -- queda como Referencia, no como
    Regla aplicada."""
    regla_aplicada, referencia = construir_citas(
        [_resultado(tipo="referencia", fuente_id="EST-001", seccion="§2", prioridad=3)]
    )

    assert regla_aplicada is None
    assert referencia == "Referencia: EST-001, cap. §2"


def test_construir_citas_separa_regla_aplicada_de_referencia_a_la_vez() -> None:
    fragmentos = [
        _resultado(tipo="regla_interna", fuente_id="POL-001", seccion="§3"),
        _resultado(tipo="referencia", fuente_id="EST-001", seccion=None, pagina=2),
    ]

    regla_aplicada, referencia = construir_citas(fragmentos)

    assert regla_aplicada == "Regla aplicada: POL-001 §3 (v2026-01)"
    assert referencia == "Referencia: EST-001, pág. 2"


def test_construir_citas_sin_fragmentos_no_da_ninguna_cita() -> None:
    assert construir_citas([]) == (None, None)


def test_construir_citas_toma_el_primero_de_cada_categoria() -> None:
    """Ya viene ordenado por prioridad/similitud (buscar_fragmentos) -- si
    hay dos regla_interna, se cita la primera, no la de mejor puntuación
    individual explícita."""
    fragmentos = [
        _resultado(tipo="regla_interna", fuente_id="POL-001", seccion="§3"),
        _resultado(tipo="regla_interna", fuente_id="POL-002", seccion="§1"),
    ]

    regla_aplicada, _referencia = construir_citas(fragmentos)

    assert regla_aplicada == "Regla aplicada: POL-001 §3 (v2026-01)"
