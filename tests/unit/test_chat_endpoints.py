"""P-14 (Bloque 2): endpoints /chat/conversaciones/* -- recuperación RAG,
adjuntos (OCR/parsers) y aislamiento entre usuarios (RNF-19).
"""

import os

import httpx
import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

os.environ.setdefault("API_SECRET_KEY", "clave-de-prueba")

from api import main  # noqa: E402
from parsers.segmentos import SegmentoTexto  # noqa: E402
from rag.ingesta import ingerir_fragmentos  # noqa: E402

COLECCION = "chat-prueba"
_PALABRAS_CLAVE = ["viaticos", "limite", "diario", "internacional", "cuadre", "otro"]
DIMENSION = len(_PALABRAS_CLAVE)


def _embedding_falso(texto: str) -> list[float]:
    texto_normalizado = texto.lower()
    return [float(texto_normalizado.count(p)) for p in _PALABRAS_CLAVE]


class _RespuestaFalsa:
    def __init__(self, cuerpo: dict) -> None:
        self._cuerpo = cuerpo

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._cuerpo


def _respuesta_chat_falsa(contenido: str) -> _RespuestaFalsa:
    return _RespuestaFalsa(
        {
            "message": {"content": contenido},
            "prompt_eval_count": 10,
            "eval_count": 5,
            "total_duration": 1_000_000_000,
        }
    )


@pytest.fixture()
def cliente_qdrant() -> QdrantClient:
    return QdrantClient(":memory:")


@pytest.fixture()
def cliente(sesion_bd, cliente_qdrant):
    main.app.dependency_overrides[main.obtener_sesion] = lambda: sesion_bd
    main.app.dependency_overrides[main.obtener_cliente_qdrant] = lambda: cliente_qdrant
    main.app.dependency_overrides[main.obtener_funcion_embedding] = lambda: _embedding_falso
    main.app.dependency_overrides[main.obtener_coleccion_kb] = lambda: COLECCION
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


def _token(cliente: TestClient, email: str, password: str = "cambiar123") -> str:
    respuesta = cliente.post("/auth/login", json={"email": email, "password": password})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["access_token"]


def _encabezado(cliente: TestClient, email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(cliente, email)}"}


def _sembrar_fragmento(cliente_qdrant: QdrantClient) -> None:
    ingerir_fragmentos(
        cliente_qdrant,
        coleccion=COLECCION,
        fuente_id="POL-001",
        fragmentos=[("f1", "El límite diario de viáticos es de Q300 (política POL-001).")],
        funcion_embedding=_embedding_falso,
        dimension=DIMENSION,
    )


def test_crear_conversacion_devuelve_una_conversacion_vacia(cliente: TestClient) -> None:
    respuesta = cliente.post("/chat/conversaciones", headers=_encabezado(cliente, "analista@local"))
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["titulo"] is None
    assert "id" in cuerpo


def test_listar_conversaciones_solo_muestra_las_del_usuario_autenticado(
    cliente: TestClient,
) -> None:
    cliente.post("/chat/conversaciones", headers=_encabezado(cliente, "analista@local"))
    cliente.post("/chat/conversaciones", headers=_encabezado(cliente, "revisor@local"))

    respuesta = cliente.get("/chat/conversaciones", headers=_encabezado(cliente, "analista@local"))

    assert respuesta.status_code == 200
    assert len(respuesta.json()) == 1


def test_obtener_conversacion_de_otro_usuario_da_404(cliente: TestClient) -> None:
    creada = cliente.post(
        "/chat/conversaciones", headers=_encabezado(cliente, "analista@local")
    ).json()

    respuesta = cliente.get(
        f"/chat/conversaciones/{creada['id']}", headers=_encabezado(cliente, "revisor@local")
    )

    assert respuesta.status_code == 404


def test_obtener_conversacion_inexistente_da_404(cliente: TestClient) -> None:
    respuesta = cliente.get(
        "/chat/conversaciones/00000000-0000-0000-0000-000000000000",
        headers=_encabezado(cliente, "analista@local"),
    )
    assert respuesta.status_code == 404


def test_enviar_mensaje_con_fragmento_relevante_cita_la_fuente(
    cliente: TestClient, cliente_qdrant, monkeypatch
) -> None:
    _sembrar_fragmento(cliente_qdrant)
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, *, json, timeout: _respuesta_chat_falsa(
            "Según POL-001, el límite diario de viáticos es Q300."
        ),
    )
    encabezado = _encabezado(cliente, "analista@local")
    conversacion = cliente.post("/chat/conversaciones", headers=encabezado).json()

    respuesta = cliente.post(
        f"/chat/conversaciones/{conversacion['id']}/mensajes",
        headers=encabezado,
        data={"contenido": "¿Cuál es el límite diario de viáticos?"},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["rol"] == "assistant"
    assert "POL-001" in cuerpo["contenido"]
    assert cuerpo["fuentes_citadas"] is not None
    assert cuerpo["fuentes_citadas"][0]["fuente_id"] == "POL-001"


def test_enviar_mensaje_sin_fragmentos_relevantes_no_inventa_fuente(
    cliente: TestClient, monkeypatch
) -> None:
    """R-17: la colección está vacía -- sin fragmentos, no debe citar nada."""
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, *, json, timeout: _respuesta_chat_falsa(
            "No tengo información sobre esto en la base de conocimiento."
        ),
    )
    encabezado = _encabezado(cliente, "analista@local")
    conversacion = cliente.post("/chat/conversaciones", headers=encabezado).json()

    respuesta = cliente.post(
        f"/chat/conversaciones/{conversacion['id']}/mensajes",
        headers=encabezado,
        data={"contenido": "¿Algo que no está en ningún lado?"},
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["fuentes_citadas"] is None


def test_enviar_mensaje_guarda_el_mensaje_del_usuario_y_pone_titulo(
    cliente: TestClient, sesion_bd, monkeypatch
) -> None:
    monkeypatch.setattr(httpx, "post", lambda url, *, json, timeout: _respuesta_chat_falsa("ok"))
    encabezado = _encabezado(cliente, "analista@local")
    conversacion = cliente.post("/chat/conversaciones", headers=encabezado).json()

    cliente.post(
        f"/chat/conversaciones/{conversacion['id']}/mensajes",
        headers=encabezado,
        data={"contenido": "Primera pregunta"},
    )

    detalle = cliente.get(f"/chat/conversaciones/{conversacion['id']}", headers=encabezado).json()
    assert detalle["titulo"] == "Primera pregunta"
    assert [m["rol"] for m in detalle["mensajes"]] == ["user", "assistant"]
    assert detalle["mensajes"][0]["contenido"] == "Primera pregunta"


def test_enviar_mensaje_con_adjunto_de_imagen_usa_su_texto(
    cliente: TestClient, monkeypatch
) -> None:
    llamada = {}

    def _post_falso(url, *, json, timeout):
        llamada["mensajes"] = json["messages"]
        return _respuesta_chat_falsa("ok")

    def _procesar_documento_falso(contenido, *, tipo_archivo, funcion_ocr=None):
        from ocr.modelos import Linea, Palabra, ResultadoPagina

        palabra = Palabra(texto="hola", izquierda=0, arriba=0, ancho=1, alto=1, confianza=90.0)
        linea = Linea(texto="texto de la imagen adjunta", palabras=(palabra,))
        return [
            ResultadoPagina(
                numero=1,
                ancho_px=10,
                alto_px=10,
                lineas=(linea,),
                palabras=(palabra,),
                confianza_media=90.0,
            )
        ]

    monkeypatch.setattr(httpx, "post", _post_falso)
    monkeypatch.setattr("comun.chat.procesar_documento", _procesar_documento_falso)

    encabezado = _encabezado(cliente, "analista@local")
    conversacion = cliente.post("/chat/conversaciones", headers=encabezado).json()

    respuesta = cliente.post(
        f"/chat/conversaciones/{conversacion['id']}/mensajes",
        headers=encabezado,
        data={"contenido": "¿Qué dice esta imagen?"},
        files={"adjunto": ("foto.png", b"contenido-falso-de-imagen", "image/png")},
    )

    assert respuesta.status_code == 200
    assert "texto de la imagen adjunta" in llamada["mensajes"][-1]["content"]


def test_adjunto_nunca_se_agrega_a_la_base_de_conocimiento(
    cliente: TestClient, cliente_qdrant, sesion_bd, monkeypatch
) -> None:
    """R-18: tras enviar un adjunto, no debe quedar ningún punto nuevo en la
    colección de Qdrant ni ninguna fila de FuenteConocimiento."""
    from comun.modelos import FuenteConocimiento

    monkeypatch.setattr(httpx, "post", lambda url, *, json, timeout: _respuesta_chat_falsa("ok"))
    monkeypatch.setattr(
        "comun.chat.leer_texto_docx",
        lambda archivo: [SegmentoTexto(texto="contenido del word adjunto", ubicacion="p0")],
    )

    encabezado = _encabezado(cliente, "analista@local")
    conversacion = cliente.post("/chat/conversaciones", headers=encabezado).json()

    cliente.post(
        f"/chat/conversaciones/{conversacion['id']}/mensajes",
        headers=encabezado,
        data={"contenido": "¿Qué dice este documento?"},
        files={
            "adjunto": (
                "memo.docx",
                b"contenido-falso-de-word",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert sesion_bd.query(FuenteConocimiento).count() == 0
    conteo_puntos = (
        cliente_qdrant.count(collection_name=COLECCION).count
        if (cliente_qdrant.collection_exists(COLECCION))
        else 0
    )
    assert conteo_puntos == 0


def test_registra_el_uso_del_llm_del_chat(
    cliente: TestClient, cliente_qdrant, sesion_bd, monkeypatch
) -> None:
    from comun.modelos import UsoLlm

    _sembrar_fragmento(cliente_qdrant)
    monkeypatch.setattr(httpx, "post", lambda url, *, json, timeout: _respuesta_chat_falsa("ok"))
    encabezado = _encabezado(cliente, "analista@local")
    conversacion = cliente.post("/chat/conversaciones", headers=encabezado).json()

    cliente.post(
        f"/chat/conversaciones/{conversacion['id']}/mensajes",
        headers=encabezado,
        data={"contenido": "una pregunta"},
    )

    filas = sesion_bd.query(UsoLlm).filter(UsoLlm.caso_uso == "chat_kb").all()
    assert len(filas) == 2  # 1 de embeddings (búsqueda) + 1 del LLM (respuesta)
    assert all(f.analisis_id is None for f in filas)


# --- Bloque 4 (cierre): el chat es accesible a cualquier rol autenticado ----


@pytest.mark.parametrize(
    "email",
    ["analista@local", "revisor@local", "curador@local", "auditor@local", "administrador@local"],
)
def test_chat_no_tiene_permiso_propio_cualquier_rol_puede_usarlo(
    cliente: TestClient, email: str
) -> None:
    """A diferencia del Dashboard del Administrador (dashboard:ver, P-13),
    el chat no exige ningún permiso -- solo sesión iniciada (CU-12, HU-31),
    igual que Historial."""
    encabezado = _encabezado(cliente, email)
    assert cliente.post("/chat/conversaciones", headers=encabezado).status_code == 200
    assert cliente.get("/chat/conversaciones", headers=encabezado).status_code == 200


def test_cada_rol_solo_ve_sus_propias_conversaciones(cliente: TestClient) -> None:
    """RNF-19: aislamiento entre usuarios -- con los 5 roles creando una
    conversación cada uno, cada quien solo ve la suya."""
    correos = [
        "analista@local",
        "revisor@local",
        "curador@local",
        "auditor@local",
        "administrador@local",
    ]
    for correo in correos:
        cliente.post("/chat/conversaciones", headers=_encabezado(cliente, correo))

    for correo in correos:
        respuesta = cliente.get("/chat/conversaciones", headers=_encabezado(cliente, correo))
        assert len(respuesta.json()) == 1


def test_respuesta_vacia_del_modelo_se_reemplaza_por_un_mensaje_explicativo(
    cliente: TestClient, monkeypatch
) -> None:
    # gpt-oss puede gastar todos los tokens permitidos razonando y devolver contenido vacío.
    monkeypatch.setattr(httpx, "post", lambda url, *, json, timeout: _respuesta_chat_falsa("  "))
    encabezado = _encabezado(cliente, "analista@local")
    conversacion = cliente.post("/chat/conversaciones", headers=encabezado).json()

    respuesta = cliente.post(
        f"/chat/conversaciones/{conversacion['id']}/mensajes",
        headers=encabezado,
        data={"contenido": "Una pregunta muy larga"},
    )

    assert respuesta.status_code == 200
    contenido = respuesta.json()["contenido"]
    assert contenido.strip() != ""
    assert "reformule" in contenido.lower()


def test_mientras_el_chat_espera_a_la_ia_el_servidor_sigue_atendiendo_a_los_demas(
    cliente: TestClient, monkeypatch
) -> None:
    import threading
    import time

    # Una generación lenta no debe bloquear el servidor: antes, el endpoint async llamaba a la IA
    # de forma bloqueante y congelaba hasta el inicio de sesión de los demás usuarios.
    def _post_lento(url, *, json, timeout):
        time.sleep(1.5)
        return _respuesta_chat_falsa("respuesta lenta")

    monkeypatch.setattr(httpx, "post", _post_lento)
    encabezado = _encabezado(cliente, "analista@local")
    conversacion = cliente.post("/chat/conversaciones", headers=encabezado).json()
    hilo = threading.Thread(
        target=lambda: cliente.post(
            f"/chat/conversaciones/{conversacion['id']}/mensajes",
            headers=encabezado,
            data={"contenido": "Pregunta lenta"},
        )
    )
    hilo.start()
    time.sleep(0.4)

    inicio = time.monotonic()
    respuesta = cliente.get("/health")
    espera = time.monotonic() - inicio
    hilo.join()

    assert respuesta.status_code == 200
    assert espera < 0.8, f"el servidor estuvo bloqueado {espera:.1f} s mientras el chat esperaba"

