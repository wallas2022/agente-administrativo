"""P-13 (Bloque 1, RF-21/RNF-15): una llamada simulada al LLM/embeddings
genera su fila de uso con los valores correctos; un timeout o un error
queda registrado como tal y nunca rompe a quien llama.
"""

import uuid

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from comun.modelos import Area, Base, Rol, UsoLlm, Usuario
from comun.uso_llm import envolver_generar_texto, envolver_obtener_embedding, registrar_uso_llm


@pytest.fixture()
def sesion() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


@pytest.fixture()
def usuario_y_area(sesion: Session) -> tuple[Usuario, Area]:
    area = Area(nombre="Contabilidad")
    rol = Rol(nombre="analista")
    sesion.add_all([area, rol])
    sesion.flush()
    usuario = Usuario(nombre="Ana", email="ana@local", area_id=area.id, rol_id=rol.id)
    sesion.add(usuario)
    sesion.commit()
    return usuario, area


def test_registrar_uso_llm_crea_una_fila_con_los_valores_correctos(sesion, usuario_y_area) -> None:
    usuario, area = usuario_y_area
    analisis_id = uuid.uuid4()
    from rag.cliente_llm import MetricasOllama

    metricas = MetricasOllama(
        modelo="gpt-oss:20b",
        tokens_entrada=120,
        tokens_salida=45,
        duracion_total_ms=5000,
        duracion_carga_ms=1000,
        duracion_lectura_ms=500,
        duracion_generacion_ms=3500,
    )

    registrar_uso_llm(
        sesion,
        usuario_id=usuario.id,
        area_id=area.id,
        analisis_id=analisis_id,
        caso_uso="contable",
        modelo="gpt-oss:20b",
        resultado="ok",
        metricas=metricas,
    )
    sesion.commit()

    fila = sesion.query(UsoLlm).one()
    assert fila.usuario_id == usuario.id
    assert fila.area_id == area.id
    assert fila.analisis_id == analisis_id
    assert fila.caso_uso == "contable"
    assert fila.modelo == "gpt-oss:20b"
    assert fila.resultado == "ok"
    assert fila.tokens_entrada == 120
    assert fila.tokens_salida == 45
    assert fila.duracion_total_ms == 5000


def test_registrar_uso_llm_nunca_propaga_un_error(sesion, usuario_y_area, monkeypatch) -> None:
    """RNF-15: un fallo al registrar el uso no debe frenar el análisis."""
    usuario, area = usuario_y_area

    def _add_que_falla(_fila):
        raise RuntimeError("la base de datos no responde")

    monkeypatch.setattr(sesion, "add", _add_que_falla)

    # No debe lanzar, a pesar de que sesion.add() falla.
    registrar_uso_llm(
        sesion,
        usuario_id=usuario.id,
        area_id=area.id,
        analisis_id=None,
        caso_uso="contable",
        modelo="gpt-oss:20b",
        resultado="ok",
        metricas=None,
    )


# --- envolver_generar_texto -------------------------------------------------


def test_envolver_generar_texto_registra_ok_con_las_metricas_reales(
    sesion, usuario_y_area, monkeypatch
) -> None:
    usuario, area = usuario_y_area

    class _RespuestaFalsa:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {
                "message": {"content": "texto generado"},
                "prompt_eval_count": 10,
                "eval_count": 20,
                "total_duration": 1_000_000_000,
            }

    monkeypatch.setattr(httpx, "post", lambda url, *, json, timeout: _RespuestaFalsa())

    funcion = envolver_generar_texto(
        sesion=sesion,
        usuario_id=usuario.id,
        area_id=area.id,
        analisis_id=None,
        caso_uso="redaccion",
        modelo="gpt-oss:20b",
    )
    resultado = funcion("prompt de prueba")
    sesion.commit()

    assert resultado == "texto generado"
    fila = sesion.query(UsoLlm).one()
    assert fila.caso_uso == "redaccion"
    assert fila.resultado == "ok"
    assert fila.tokens_entrada == 10
    assert fila.tokens_salida == 20


def test_envolver_generar_texto_registra_timeout_y_relanza(
    sesion, usuario_y_area, monkeypatch
) -> None:
    usuario, area = usuario_y_area

    def _post_que_expira(url, *, json, timeout):
        raise httpx.TimeoutException("se agotó el tiempo")

    monkeypatch.setattr(httpx, "post", _post_que_expira)

    funcion = envolver_generar_texto(
        sesion=sesion,
        usuario_id=usuario.id,
        area_id=area.id,
        analisis_id=None,
        caso_uso="contable",
        modelo="gpt-oss:20b",
    )

    with pytest.raises(httpx.TimeoutException):
        funcion("prompt de prueba")
    sesion.commit()

    fila = sesion.query(UsoLlm).one()
    assert fila.resultado == "timeout"
    assert fila.tokens_entrada is None


def test_envolver_generar_texto_registra_error_generico_y_relanza(
    sesion, usuario_y_area, monkeypatch
) -> None:
    usuario, area = usuario_y_area

    def _post_que_falla(url, *, json, timeout):
        raise httpx.ConnectError("no se pudo conectar")

    monkeypatch.setattr(httpx, "post", _post_que_falla)

    funcion = envolver_generar_texto(
        sesion=sesion,
        usuario_id=usuario.id,
        area_id=area.id,
        analisis_id=None,
        caso_uso="contable",
        modelo="gpt-oss:20b",
    )

    with pytest.raises(httpx.ConnectError):
        funcion("prompt de prueba")
    sesion.commit()

    fila = sesion.query(UsoLlm).one()
    assert fila.resultado == "error"


# --- envolver_obtener_embedding ---------------------------------------------


def test_envolver_obtener_embedding_registra_ok(sesion, usuario_y_area, monkeypatch) -> None:
    usuario, area = usuario_y_area

    class _RespuestaFalsa:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"embeddings": [[0.1, 0.2]], "prompt_eval_count": 4}

    monkeypatch.setattr(httpx, "post", lambda url, *, json, timeout: _RespuestaFalsa())

    funcion = envolver_obtener_embedding(
        sesion=sesion,
        usuario_id=usuario.id,
        area_id=area.id,
        analisis_id=None,
        caso_uso="embeddings_kb",
        modelo="bge-m3",
    )
    resultado = funcion("texto")
    sesion.commit()

    assert resultado == [0.1, 0.2]
    fila = sesion.query(UsoLlm).one()
    assert fila.caso_uso == "embeddings_kb"
    assert fila.resultado == "ok"
    assert fila.tokens_entrada == 4


def test_envolver_obtener_embedding_registra_timeout(sesion, usuario_y_area, monkeypatch) -> None:
    usuario, area = usuario_y_area

    def _post_que_expira(url, *, json, timeout):
        raise httpx.TimeoutException("se agotó el tiempo")

    monkeypatch.setattr(httpx, "post", _post_que_expira)

    funcion = envolver_obtener_embedding(
        sesion=sesion,
        usuario_id=usuario.id,
        area_id=area.id,
        analisis_id=None,
        caso_uso="embeddings_busqueda",
        modelo="bge-m3",
    )

    with pytest.raises(httpx.TimeoutException):
        funcion("texto")
    sesion.commit()

    fila = sesion.query(UsoLlm).one()
    assert fila.resultado == "timeout"
