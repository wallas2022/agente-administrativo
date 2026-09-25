from qdrant_client import QdrantClient

from rag.busqueda import buscar_fragmentos
from rag.ingesta import ingerir_fragmentos

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
