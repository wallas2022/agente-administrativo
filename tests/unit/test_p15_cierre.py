"""P-15 Bloque 6: pruebas de cierre de la aprobación de fuentes (con dobles, sin servicios reales).

- PDF de 300 páginas: la API responde al instante y el worker indexa sin exceder el tope.
- ReadTimeout de embeddings y objeto ausente: la fuente queda en error_indexacion con el motivo
  visible en el listado, y se puede reintentar.
- La búsqueda (chat, CU-01) sigue viendo solo lo vigente mientras se reindexa.
"""

import os
import time
import uuid

import boto3
import httpx
import pymupdf
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from qdrant_client import QdrantClient

os.environ.setdefault("API_SECRET_KEY", "clave-de-prueba")

from api import main  # noqa: E402
from comun.almacenamiento import descargar_objeto  # noqa: E402
from comun.modelos import Bitacora, Fragmento, FuenteConocimiento  # noqa: E402
from curaduria.aprobacion import procesar_indexacion  # noqa: E402
from curaduria.extraccion import estimar_tokens  # noqa: E402
from rag import cliente_embeddings  # noqa: E402
from rag.busqueda import buscar_fragmentos  # noqa: E402
from rag.cliente_embeddings import DIMENSION_BGE_M3  # noqa: E402

COLECCION = "kb_prueba_p15_cierre"
TOPE_TOKENS = 450
LIMITE_BATCH_OLLAMA = 2048  # "input too large (batch 2048)" visto en stage
PAGINAS = 300


def _pdf_de_300_paginas() -> bytes:
    documento = pymupdf.open()
    for numero in range(1, PAGINAS + 1):
        pagina = documento.new_page()
        if numero == 1:  # una sola sección que abarca todo el documento
            pagina.insert_text((40, 40), "§1 Manual extenso", fontsize=12)
        cuerpo = " ".join(f"término{numero}_{n}" for n in range(700))
        pagina.insert_textbox(pymupdf.Rect(30, 60, 565, 810), cuerpo, fontsize=7)
    contenido = documento.tobytes()
    documento.close()
    return contenido


def _vector(texto: str) -> list[float]:
    return [float(len(texto) % 7), 1.0, 0.0, 0.0] + [0.0] * (DIMENSION_BGE_M3 - 4)


@pytest.fixture()
def entorno(sesion_bd):
    with mock_aws():
        cliente_s3 = boto3.client("s3", region_name="us-east-1")
        cliente_s3.create_bucket(Bucket="documentos")
        cliente_s3.create_bucket(Bucket="conocimiento")
        qdrant = QdrantClient(":memory:")
        # Por defecto el "encolador" solo registra la tarea (no la ejecuta): la API no la espera.
        encolados: list[tuple[str, str]] = []
        comportamiento = {"ejecutor": None}

        def _encolador():
            def _encolar(fuente_id: str, usuario_id: str) -> str:
                encolados.append((fuente_id, usuario_id))
                if comportamiento["ejecutor"] is not None:
                    comportamiento["ejecutor"](fuente_id, usuario_id)
                return "tarea-falsa"

            return _encolar

        def _worker(*, embedding=None, embedding_lote=None, tamano_lote=16):
            def _ejecutar(fuente_id: str, usuario_id: str) -> None:
                fuente = sesion_bd.get(FuenteConocimiento, uuid.UUID(fuente_id))
                procesar_indexacion(
                    sesion_bd,
                    qdrant,
                    fuente_id=fuente.id,
                    usuario_id=uuid.UUID(usuario_id),
                    obtener_contenido=lambda: descargar_objeto(
                        cliente_s3, "conocimiento", fuente.archivo
                    ),
                    funcion_embedding=embedding or _vector,
                    funcion_embedding_lote=embedding_lote,
                    tamano_lote=tamano_lote,
                    dimension=DIMENSION_BGE_M3,
                    coleccion=COLECCION,
                )

            return _ejecutar

        main.app.dependency_overrides[main.obtener_sesion] = lambda: sesion_bd
        main.app.dependency_overrides[main.obtener_cliente_almacenamiento] = lambda: cliente_s3
        main.app.dependency_overrides[main.obtener_cliente_qdrant] = lambda: qdrant
        main.app.dependency_overrides[main.obtener_coleccion_kb] = lambda: COLECCION
        main.app.dependency_overrides[main.obtener_encolador_indexacion] = _encolador
        with TestClient(main.app, raise_server_exceptions=False) as cliente:
            yield cliente, cliente_s3, qdrant, encolados, comportamiento, _worker
        main.app.dependency_overrides.clear()


def _autorizacion(cliente: TestClient) -> dict[str, str]:
    r = cliente.post("/auth/login", json={"email": "curador@local", "password": "cambiar123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _subir(
    cliente, encabezados, contenido: bytes, *, version: str = "1", fuente_id: str = "MAN-300"
):
    r = cliente.post(
        "/curaduria/fuentes",
        headers=encabezados,
        data={
            "fuente_id": fuente_id,
            "titulo": "Manual extenso",
            "tipo": "política (Word)",
            "version": version,
            "vigente_desde": "2026-01-15",
            "dueno": "Jefatura de Contabilidad",
        },
        files={"archivo": ("manual.pdf", contenido, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _estado(cliente, encabezados, fuente_id: str) -> dict:
    listado = cliente.get("/curaduria/fuentes", headers=encabezados).json()
    return next(f for f in listado if f["id"] == fuente_id)


def test_pdf_de_300_paginas_no_bloquea_la_api_y_el_worker_indexa_sin_exceder_el_tope(
    entorno, sesion_bd, capsys
) -> None:
    cliente, _s3, qdrant, encolados, _cmp, _worker = entorno
    encabezados = _autorizacion(cliente)
    fuente = _subir(cliente, encabezados, _pdf_de_300_paginas())

    inicio = time.monotonic()
    respuesta = cliente.post(f"/curaduria/fuentes/{fuente['id']}/aprobar", headers=encabezados)
    tiempo_api = time.monotonic() - inicio

    assert respuesta.status_code == 202
    assert respuesta.json()["estado"] == "indexando"
    assert tiempo_api < 2.0  # la API no indexa: solo encola
    assert len(encolados) == 1
    assert _estado(cliente, encabezados, fuente["id"])["estado"] == "indexando"

    tamanos: list[int] = []
    llamadas: list[int] = []

    def embedding_lote(textos: list[str]) -> list[list[float]]:
        llamadas.append(len(textos))
        for texto in textos:
            tokens = estimar_tokens(texto)
            tamanos.append(tokens)
            assert tokens <= LIMITE_BATCH_OLLAMA, "input too large"  # lo que rechazaba Ollama
            assert tokens <= TOPE_TOKENS, "fragmento sobre el tope: se truncaría"
        return [_vector(t) for t in textos]

    inicio = time.monotonic()
    _worker(embedding_lote=embedding_lote)(*encolados[0])
    tiempo_worker = time.monotonic() - inicio

    fila = _estado(cliente, encabezados, fuente["id"])
    assert fila["estado"] == "vigente"
    assert fila["fragmentos_procesados"] == fila["fragmentos_total"] == len(tamanos)
    assert len(tamanos) >= PAGINAS
    assert qdrant.count(COLECCION).count == len(tamanos)
    assert max(llamadas) <= 16
    with capsys.disabled():
        print(
            f"\n[P15-B6] paginas={PAGINAS} fragmentos={len(tamanos)} "
            f"max_tokens_est={max(tamanos)} lotes={len(llamadas)} "
            f"api_ms={tiempo_api * 1000:.0f} worker_s={tiempo_worker:.1f}"
        )


def _respuesta_ollama_falsa(textos: list[str]):
    class _R:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"embeddings": [_vector(t) for t in textos]}

    return _R()


def test_read_timeout_de_embeddings_deja_error_indexacion_visible_y_se_reintenta(
    entorno, sesion_bd, monkeypatch
) -> None:
    cliente, _s3, _qdrant, _encolados, comportamiento, worker = entorno
    monkeypatch.setattr(cliente_embeddings.time, "sleep", lambda _s: None)
    monkeypatch.setenv("EMBEDDINGS_REINTENTOS", "2")
    llamadas = {"n": 0}

    def post_que_agota_el_tiempo(url: str, *, json: dict, timeout: float):
        llamadas["n"] += 1
        raise httpx.ReadTimeout("The read operation timed out")

    monkeypatch.setattr(httpx, "post", post_que_agota_el_tiempo)
    comportamiento["ejecutor"] = worker(embedding_lote=cliente_embeddings.obtener_embeddings_lote)
    encabezados = _autorizacion(cliente)
    pdf = _pdf_de_300_paginas()
    fuente = _subir(cliente, encabezados, pdf)

    respuesta = cliente.post(f"/curaduria/fuentes/{fuente['id']}/aprobar", headers=encabezados)

    assert respuesta.status_code == 202  # la API no ve la falla: ocurre en el worker
    fila = _estado(cliente, encabezados, fuente["id"])
    assert fila["estado"] == "error_indexacion"
    assert "tardó demasiado" in fila["motivo_error"]  # lo que muestra la UI junto a "Reintentar"
    assert llamadas["n"] == 3  # 1 intento + 2 reintentos, y se rinde
    assert sesion_bd.query(Fragmento).filter_by(fuente_id=uuid.UUID(fuente["id"])).count() == 0
    acciones = {
        b.accion for b in sesion_bd.query(Bitacora).filter_by(entidad_id=uuid.UUID(fuente["id"]))
    }
    assert {"fuente_indexacion_iniciada", "fuente_indexacion_fallida"} <= acciones

    # Ollama vuelve a responder: "Reintentar" (el mismo endpoint) la deja vigente.
    def post_sano(url: str, *, json: dict, timeout: float):
        return _respuesta_ollama_falsa(json["input"])

    monkeypatch.setattr(httpx, "post", post_sano)
    reintento = cliente.post(f"/curaduria/fuentes/{fuente['id']}/aprobar", headers=encabezados)

    assert reintento.status_code == 202
    fila = _estado(cliente, encabezados, fuente["id"])
    assert fila["estado"] == "vigente"
    assert fila["motivo_error"] is None
    assert "fuente_indexacion_reintentada" in {
        b.accion for b in sesion_bd.query(Bitacora).filter_by(entidad_id=uuid.UUID(fuente["id"]))
    }


def test_objeto_ausente_se_informa_al_aprobar_y_tambien_si_desaparece_en_la_cola(
    entorno, monkeypatch
) -> None:
    cliente, s3, _qdrant, _encolados, comportamiento, worker = entorno
    comportamiento["ejecutor"] = worker()
    encabezados = _autorizacion(cliente)
    fuente = _subir(cliente, encabezados, _pdf_de_300_paginas())
    llave = s3.list_objects_v2(Bucket="conocimiento")["Contents"][0]["Key"]
    s3.delete_object(Bucket="conocimiento", Key=llave)
    mensaje = "El archivo de la fuente no está en el almacenamiento; súbalo de nuevo"

    # 1. La API lo detecta antes de encolar: 409 con el mensaje.
    respuesta = cliente.post(f"/curaduria/fuentes/{fuente['id']}/aprobar", headers=encabezados)
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == mensaje
    assert _estado(cliente, encabezados, fuente["id"])["estado"] == "borrador"

    # 2. El archivo desaparece entre el encolado y el worker: error_indexacion con el mismo mensaje.
    monkeypatch.setattr(main.almacenamiento, "existe_objeto", lambda *_a, **_k: True)
    respuesta = cliente.post(f"/curaduria/fuentes/{fuente['id']}/aprobar", headers=encabezados)
    assert respuesta.status_code == 202
    fila = _estado(cliente, encabezados, fuente["id"])
    assert (fila["estado"], fila["motivo_error"]) == ("error_indexacion", mensaje)


def test_la_busqueda_solo_ve_lo_vigente_mientras_se_reindexa(entorno, sesion_bd) -> None:
    """Chat y CU-01 leen con filtro estado == "vigente": reindexar no debe dejarlos sin contexto."""
    cliente, _s3, qdrant, _encolados, comportamiento, worker = entorno
    encabezados = _autorizacion(cliente)
    pdf_v1 = _pdf_de_300_paginas()
    v1 = _subir(cliente, encabezados, pdf_v1, version="1")
    comportamiento["ejecutor"] = worker()
    cliente.post(f"/curaduria/fuentes/{v1['id']}/aprobar", headers=encabezados)
    assert _estado(cliente, encabezados, v1["id"])["estado"] == "vigente"

    v2 = _subir(cliente, encabezados, pdf_v1, version="2")
    visto_durante: dict[str, set[str]] = {}

    def embedding_que_busca(texto: str) -> list[float]:
        if not visto_durante:
            resultados = buscar_fragmentos(
                qdrant,
                coleccion=COLECCION,
                texto_consulta="manual",
                funcion_embedding=_vector,
                top_k=3,
            )
            visto_durante["versiones"] = {r.version for r in resultados}
        return _vector(texto)

    comportamiento["ejecutor"] = worker(embedding=embedding_que_busca)
    cliente.post(f"/curaduria/fuentes/{v2['id']}/aprobar", headers=encabezados)

    assert visto_durante["versiones"] == {"1"}  # mientras indexa v2, la búsqueda sigue en v1
    despues = buscar_fragmentos(
        qdrant, coleccion=COLECCION, texto_consulta="manual", funcion_embedding=_vector, top_k=3
    )
    assert {r.version for r in despues} == {"2"}
    assert _estado(cliente, encabezados, v1["id"])["estado"] == "obsoleta"
