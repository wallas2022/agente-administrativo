"""Pruebas de la ruta SSE de fase 2 de CU-02 (RF-07, RF-12): mejora de
redacción por párrafo, streaming -- GET /analisis/{id}/mejorar-stream.
Contra la API real (TestClient), no la función de dominio suelta (ver
tests/unit/test_redaccion_mejora.py).
"""

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("API_SECRET_KEY", "clave-de-prueba")

from api import main  # noqa: E402
from comun.estados import EstadoDocumento  # noqa: E402
from comun.modelos import Base, Documento, Hallazgo  # noqa: E402
from comun.semillas import sembrar_datos_de_prueba  # noqa: E402

COLECCION_PRUEBA = "kb_prueba_cu02_stream"

# Sin cifras/fechas/nombres propios -- cualquier reescritura del LLM pasa la
# guardia de integridad sin importar qué tanto cambie la redacción. >=25
# palabras para que el Bloque 4 no lo salte.
_PARRAFO_SIN_DATOS_SENSIBLES = (
    "hola, este es un parrafo de prueba bastante corto y sencillo que de todas "
    "formas tiene que llegar a veinticinco palabras para que no se salte el llamado al modelo."
)
_PARRAFO_CON_MONTO = (
    "el ajuste fue por Q 100.00 segun lo revisado por el area correspondiente "
    "hace ya varias semanas, antes del cierre contable del periodo anterior, "
    "y quedo debidamente documentado en el expediente correspondiente."
)


def _embedding_falso(_texto: str) -> list[float]:
    return [0.1] * 8


def _sin_coincidencias_lt(_texto: str) -> list:
    return []


def _llm_que_reescribe(prompt: str) -> str:
    if "institucional, completo" in prompt:
        return "Hola, este es un párrafo de prueba corregido, versión formal."
    return "Párrafo de prueba corregido, versión breve."


def _llm_que_ignora_el_monto(prompt: str) -> str:
    # Ambas opciones pierden "Q 100.00" -- deben activar la guardia (RNF-03)
    # y descartarse las dos, conservando el párrafo base.
    if "institucional, completo" in prompt:
        return "El ajuste fue aprobado según lo revisado, de forma institucional."
    return "El ajuste fue aprobado hace varias semanas."


@pytest.fixture()
def fabrica():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    fabrica_sesion = sessionmaker(bind=engine)
    sesion = fabrica_sesion()
    sembrar_datos_de_prueba(sesion)
    sesion.commit()
    sesion.close()
    return fabrica_sesion


@pytest.fixture()
def cliente(fabrica, cliente_s3_bucket, request):
    funcion_llm = getattr(request, "param", _llm_que_reescribe)

    def _encolador_falso(documento_id: str, analisis_id: str) -> str:
        return "tarea-de-prueba"

    cliente_qdrant = QdrantClient(":memory:")

    main.app.dependency_overrides[main.obtener_sesion] = lambda: fabrica()
    main.app.dependency_overrides[main.obtener_fabrica_sesion_stream] = lambda: fabrica
    main.app.dependency_overrides[main.obtener_cliente_almacenamiento] = lambda: cliente_s3_bucket
    main.app.dependency_overrides[main.obtener_encolador] = lambda: _encolador_falso
    main.app.dependency_overrides[main.obtener_cliente_qdrant] = lambda: cliente_qdrant
    main.app.dependency_overrides[main.obtener_funcion_embedding] = lambda: _embedding_falso
    main.app.dependency_overrides[main.obtener_coleccion_kb] = lambda: COLECCION_PRUEBA
    main.app.dependency_overrides[main.obtener_funcion_llm] = lambda: funcion_llm
    main.app.dependency_overrides[main.obtener_funcion_revisar_lt] = lambda: _sin_coincidencias_lt
    main.app.dependency_overrides[main.obtener_glosario_redaccion] = lambda: set()

    with TestClient(main.app) as test_client:
        yield test_client

    main.app.dependency_overrides.clear()


def _token(cliente: TestClient, email: str, password: str = "cambiar123") -> str:
    respuesta = cliente.post("/auth/login", json={"email": email, "password": password})
    assert respuesta.status_code == 200
    return respuesta.json()["access_token"]


def _cargar_documento_redaccion(
    cliente: TestClient, encabezados: dict[str, str], *, contenido: str, accion: str = "corregir"
) -> str:
    """Sube `contenido` como documento .txt y completa un análisis
    'redaccion' -- mismo flujo que usaría el frontend, sin invocar al
    worker (Celery está mockeado en la fixture `cliente`)."""
    respuesta = cliente.post(
        "/documentos/iniciar",
        headers=encabezados,
        json={
            "nombre_original": "texto-pegado.txt",
            "tipo_archivo": "txt",
            "tamano_bytes": len(contenido.encode("utf-8")),
        },
    )
    assert respuesta.status_code == 200
    inicio = respuesta.json()
    documento_id, upload_id, llave = (
        inicio["documento_id"],
        inicio["upload_id"],
        inicio["llave_almacenamiento"],
    )

    respuesta = cliente.put(
        f"/documentos/{documento_id}/partes/1?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers=encabezados,
        content=contenido.encode("utf-8"),
    )
    assert respuesta.status_code == 200
    etag = respuesta.json()["etag"]

    respuesta = cliente.post(
        f"/documentos/{documento_id}/completar"
        f"?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers=encabezados,
        json={
            "partes": [{"numero_parte": 1, "etag": etag}],
            "tipo_revision": "redaccion",
            "tipo_documento": "Correo",
            "accion": accion,
        },
    )
    assert respuesta.status_code == 200
    return respuesta.json()["analisis_id"]


def _parsear_eventos(texto_sse: str, nombre_evento: str) -> list[dict]:
    eventos = []
    for bloque in texto_sse.split("\n\n"):
        if bloque.startswith(f"event: {nombre_evento}"):
            _, _, linea_datos = bloque.partition("data: ")
            eventos.append(json.loads(linea_datos))
    return eventos


def test_stream_persiste_mejora_sugerida_y_marca_documento_con_hallazgos(
    cliente: TestClient, fabrica
) -> None:
    encabezados = {"Authorization": f"Bearer {_token(cliente, 'analista@local')}"}
    analisis_id = _cargar_documento_redaccion(
        cliente, encabezados, contenido=_PARRAFO_SIN_DATOS_SENSIBLES
    )

    sesion = fabrica()
    documento = sesion.query(Documento).one()
    documento.estado = EstadoDocumento.EN_REVISION.value
    sesion.commit()
    sesion.close()

    respuesta = cliente.get(f"/analisis/{analisis_id}/mejorar-stream", headers=encabezados)
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("text/event-stream")
    assert "event: fin" in respuesta.text

    inicio = _parsear_eventos(respuesta.text, "inicio")
    assert inicio == [{"total_parrafos": 1}]

    opciones = _parsear_eventos(respuesta.text, "opcion")
    assert {o["estilo"] for o in opciones} == {"Formal", "Breve"}
    assert all(o["aprobada_guardia"] for o in opciones)
    assert all(o["hallazgo_id"] is not None for o in opciones)

    parrafo_fin = _parsear_eventos(respuesta.text, "parrafo_fin")
    assert len(parrafo_fin) == 1
    assert parrafo_fin[0]["tiene_opciones_aprobadas"] is True
    assert parrafo_fin[0]["omitido"] is False

    sesion = fabrica()
    hallazgos = sesion.query(Hallazgo).all()
    assert len(hallazgos) == 1
    assert hallazgos[0].estado == "pendiente"
    assert str(hallazgos[0].id) == opciones[0]["hallazgo_id"]
    cuerpo_guardado = json.loads(hallazgos[0].correccion_sugerida)
    assert {o["estilo"] for o in cuerpo_guardado["opciones"]} == {"Formal", "Breve"}

    documento = sesion.query(Documento).one()
    assert documento.estado == EstadoDocumento.CON_HALLAZGOS.value
    sesion.close()

    # Idempotencia: volver a entrar a la pantalla de resultados (p. ej. el
    # usuario recarga la página) no debe volver a llamar al LLM ni duplicar
    # el Hallazgo ya persistido.
    segunda_respuesta = cliente.get(f"/analisis/{analisis_id}/mejorar-stream", headers=encabezados)
    assert segunda_respuesta.status_code == 200
    assert '"ya_procesado": true' in segunda_respuesta.text
    assert _parsear_eventos(segunda_respuesta.text, "opcion") == []

    sesion = fabrica()
    assert sesion.query(Hallazgo).count() == 1
    sesion.close()


@pytest.mark.parametrize("cliente", [_llm_que_ignora_el_monto], indirect=True)
def test_stream_la_guardia_descarta_ambas_opciones_que_alteran_un_monto(
    cliente: TestClient, fabrica
) -> None:
    encabezados = {"Authorization": f"Bearer {_token(cliente, 'analista@local')}"}
    analisis_id = _cargar_documento_redaccion(cliente, encabezados, contenido=_PARRAFO_CON_MONTO)

    respuesta = cliente.get(f"/analisis/{analisis_id}/mejorar-stream", headers=encabezados)
    assert respuesta.status_code == 200

    opciones = _parsear_eventos(respuesta.text, "opcion")
    assert len(opciones) == 2
    assert all(not o["aprobada_guardia"] for o in opciones)

    parrafo_fin = _parsear_eventos(respuesta.text, "parrafo_fin")
    assert parrafo_fin[0]["tiene_opciones_aprobadas"] is False

    sesion = fabrica()
    hallazgos = sesion.query(Hallazgo).all()
    assert len(hallazgos) == 1
    assert hallazgos[0].estado == "sin_cambio"
    assert "guardia" in hallazgos[0].descripcion.lower()
    sesion.close()


def test_stream_omite_el_llm_en_un_parrafo_corto_y_limpio(cliente: TestClient, fabrica) -> None:
    """Bloque 4 (rendimiento): un párrafo corto sin hallazgos no debería ni
    siquiera llamar al LLM -- se verifica indirectamente: no hay eventos
    "opcion" y el párrafo queda marcado "omitido"."""
    encabezados = {"Authorization": f"Bearer {_token(cliente, 'analista@local')}"}
    analisis_id = _cargar_documento_redaccion(
        cliente, encabezados, contenido="Todo quedó en orden y sin pendientes."
    )

    respuesta = cliente.get(f"/analisis/{analisis_id}/mejorar-stream", headers=encabezados)
    assert respuesta.status_code == 200

    assert _parsear_eventos(respuesta.text, "opcion") == []
    parrafo_fin = _parsear_eventos(respuesta.text, "parrafo_fin")
    assert len(parrafo_fin) == 1
    assert parrafo_fin[0]["omitido"] is True

    sesion = fabrica()
    assert sesion.query(Hallazgo).count() == 0
    sesion.close()


def test_stream_rechaza_analisis_que_no_es_de_tipo_redaccion(cliente: TestClient) -> None:
    encabezados = {"Authorization": f"Bearer {_token(cliente, 'analista@local')}"}
    respuesta = cliente.post(
        "/documentos/iniciar",
        headers=encabezados,
        json={"nombre_original": "a.xlsx", "tipo_archivo": "xlsx", "tamano_bytes": 100},
    )
    documento_id = respuesta.json()["documento_id"]
    upload_id, llave = respuesta.json()["upload_id"], respuesta.json()["llave_almacenamiento"]

    respuesta = cliente.put(
        f"/documentos/{documento_id}/partes/1?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers=encabezados,
        content=b"contenido",
    )
    etag = respuesta.json()["etag"]

    respuesta = cliente.post(
        f"/documentos/{documento_id}/completar"
        f"?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers=encabezados,
        json={
            "partes": [{"numero_parte": 1, "etag": etag}],
            "tipo_revision": "contable",
            "periodo_cierre": "2026-01",
        },
    )
    analisis_id = respuesta.json()["analisis_id"]

    respuesta = cliente.get(f"/analisis/{analisis_id}/mejorar-stream", headers=encabezados)
    assert respuesta.status_code == 400


def test_stream_analisis_inexistente_devuelve_404(cliente: TestClient) -> None:
    encabezados = {"Authorization": f"Bearer {_token(cliente, 'analista@local')}"}
    respuesta = cliente.get(
        f"/analisis/{uuid.uuid4()}/mejorar-stream", headers=encabezados
    )
    assert respuesta.status_code == 404
