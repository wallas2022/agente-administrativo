"""Pruebas de los endpoints de consulta que necesita la UI (bloque U2):
reanudar una carga por partes (GET .../partes), listar fuentes de
conocimiento vigentes del área, y listar análisis recientes.
"""

import os
import uuid
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("API_SECRET_KEY", "clave-de-prueba")

from api import main  # noqa: E402
from comun.modelos import Area, FuenteConocimiento, Usuario, VersionDocumento  # noqa: E402


@pytest.fixture()
def cliente(sesion_bd, cliente_s3_bucket):
    def _encolador_falso(documento_id: str, analisis_id: str) -> str:
        return "tarea-de-prueba"

    main.app.dependency_overrides[main.obtener_sesion] = lambda: sesion_bd
    main.app.dependency_overrides[main.obtener_cliente_almacenamiento] = lambda: cliente_s3_bucket
    main.app.dependency_overrides[main.obtener_encolador] = lambda: _encolador_falso

    with TestClient(main.app) as test_client:
        yield test_client

    main.app.dependency_overrides.clear()


def _token(cliente: TestClient, email: str, password: str = "cambiar123") -> str:
    respuesta = cliente.post("/auth/login", json={"email": email, "password": password})
    assert respuesta.status_code == 200
    return respuesta.json()["access_token"]


def test_listar_partes_subidas_permite_saber_que_falta_para_reanudar(cliente: TestClient) -> None:
    token = _token(cliente, "analista@local")
    encabezados = {"Authorization": f"Bearer {token}"}

    respuesta = cliente.post(
        "/documentos/iniciar",
        headers=encabezados,
        json={"nombre_original": "a.xlsx", "tipo_archivo": "xlsx", "tamano_bytes": 100},
    )
    inicio = respuesta.json()
    documento_id = inicio["documento_id"]
    upload_id = inicio["upload_id"]
    llave = inicio["llave_almacenamiento"]

    respuesta = cliente.get(
        f"/documentos/{documento_id}/partes"
        f"?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers=encabezados,
    )
    assert respuesta.status_code == 200
    assert respuesta.json() == []

    cliente.put(
        f"/documentos/{documento_id}/partes/1"
        f"?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers=encabezados,
        content=b"contenido de prueba",
    )

    respuesta = cliente.get(
        f"/documentos/{documento_id}/partes"
        f"?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers=encabezados,
    )
    assert respuesta.status_code == 200
    partes = respuesta.json()
    assert len(partes) == 1
    assert partes[0]["numero_parte"] == 1
    assert partes[0]["etag"]


def test_listar_fuentes_conocimiento_solo_del_area_y_vigentes(
    cliente: TestClient, sesion_bd
) -> None:
    token_analista = _token(cliente, "analista@local")
    analista = sesion_bd.query(Usuario).filter_by(email="analista@local").one()

    otra_area = Area(nombre="Otra área")
    sesion_bd.add(otra_area)
    sesion_bd.flush()

    sesion_bd.add_all(
        [
            FuenteConocimiento(
                nombre="Política de cierre contable",
                area_id=analista.area_id,
                curador_id=analista.id,
                version="1.0",
                vigente_desde=date(2026, 1, 1),
                estado="vigente",
                ruta_archivo="kb/fuentes/politica-cierre-contable.md",
            ),
            FuenteConocimiento(
                nombre="Fuente obsoleta",
                area_id=analista.area_id,
                curador_id=analista.id,
                version="0.9",
                vigente_desde=date(2025, 1, 1),
                estado="obsoleta",
                ruta_archivo="kb/fuentes/obsoleta.md",
            ),
            FuenteConocimiento(
                nombre="Fuente de otra área",
                area_id=otra_area.id,
                curador_id=analista.id,
                version="1.0",
                vigente_desde=date(2026, 1, 1),
                estado="vigente",
                ruta_archivo="kb/fuentes/otra-area.md",
            ),
        ]
    )
    sesion_bd.commit()

    respuesta = cliente.get(
        "/fuentes-conocimiento", headers={"Authorization": f"Bearer {token_analista}"}
    )
    assert respuesta.status_code == 200
    nombres = {f["nombre"] for f in respuesta.json()}
    assert nombres == {"Política de cierre contable"}


def test_listar_analisis_recientes_del_area(cliente: TestClient, sesion_bd) -> None:
    token = _token(cliente, "analista@local")
    encabezados = {"Authorization": f"Bearer {token}"}

    respuesta = cliente.get("/analisis", headers=encabezados)
    assert respuesta.status_code == 200
    assert respuesta.json() == []

    respuesta = cliente.post(
        "/documentos/iniciar",
        headers=encabezados,
        json={"nombre_original": "cierre.xlsx", "tipo_archivo": "xlsx", "tamano_bytes": 100},
    )
    inicio = respuesta.json()
    documento_id, upload_id, llave = (
        inicio["documento_id"],
        inicio["upload_id"],
        inicio["llave_almacenamiento"],
    )
    respuesta = cliente.put(
        f"/documentos/{documento_id}/partes/1?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers=encabezados,
        content=b"x",
    )
    etag = respuesta.json()["etag"]
    respuesta = cliente.post(
        f"/documentos/{documento_id}/completar?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers=encabezados,
        json={
            "partes": [{"numero_parte": 1, "etag": etag}],
            "tipo_revision": "contable",
            "periodo_cierre": "2026-01",
        },
    )
    assert respuesta.status_code == 200, respuesta.text

    respuesta = cliente.get("/analisis", headers=encabezados)
    assert respuesta.status_code == 200
    analisis_lista = respuesta.json()
    assert len(analisis_lista) == 1
    assert analisis_lista[0]["nombre_documento"] == "cierre.xlsx"
    assert analisis_lista[0]["periodo_cierre"] == "2026-01"

    token_auditor = _token(cliente, "auditor@local")
    respuesta = cliente.get("/analisis", headers={"Authorization": f"Bearer {token_auditor}"})
    assert respuesta.status_code == 200
    assert len(respuesta.json()) == 1  # el auditor ve de todas las áreas


def test_bitacora_del_analisis_ordenada_por_fecha(cliente: TestClient, sesion_bd) -> None:
    from comun.modelos import Bitacora

    token = _token(cliente, "analista@local")
    encabezados = {"Authorization": f"Bearer {token}"}

    respuesta = cliente.post(
        "/documentos/iniciar",
        headers=encabezados,
        json={"nombre_original": "cierre.xlsx", "tipo_archivo": "xlsx", "tamano_bytes": 100},
    )
    inicio = respuesta.json()
    documento_id, upload_id, llave = (
        inicio["documento_id"],
        inicio["upload_id"],
        inicio["llave_almacenamiento"],
    )
    respuesta = cliente.put(
        f"/documentos/{documento_id}/partes/1?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers=encabezados,
        content=b"x",
    )
    etag = respuesta.json()["etag"]
    respuesta = cliente.post(
        f"/documentos/{documento_id}/completar?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers=encabezados,
        json={
            "partes": [{"numero_parte": 1, "etag": etag}],
            "tipo_revision": "contable",
            "periodo_cierre": "2026-01",
        },
    )
    analisis_id = respuesta.json()["analisis_id"]

    usuario = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    sesion_bd.add_all(
        [
            Bitacora(
                usuario_id=usuario.id,
                accion="analisis_completado",
                entidad_tipo="analisis",
                entidad_id=uuid.UUID(analisis_id),
                fecha_hora=datetime(2026, 1, 1, 10, 5, tzinfo=UTC),
            ),
            Bitacora(
                usuario_id=usuario.id,
                accion="analisis_iniciado",
                entidad_tipo="analisis",
                entidad_id=uuid.UUID(analisis_id),
                fecha_hora=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            ),
        ]
    )
    sesion_bd.commit()

    respuesta = cliente.get(f"/analisis/{analisis_id}/bitacora", headers=encabezados)
    assert respuesta.status_code == 200
    entradas = respuesta.json()
    assert [e["accion"] for e in entradas] == ["analisis_iniciado", "analisis_completado"]


def _crear_analisis_via_api(cliente: TestClient, token_analista: str) -> tuple[str, str]:
    encabezados = {"Authorization": f"Bearer {token_analista}"}
    respuesta = cliente.post(
        "/documentos/iniciar",
        headers=encabezados,
        json={"nombre_original": "cierre.xlsx", "tipo_archivo": "xlsx", "tamano_bytes": 100},
    )
    inicio = respuesta.json()
    documento_id, upload_id, llave = (
        inicio["documento_id"],
        inicio["upload_id"],
        inicio["llave_almacenamiento"],
    )
    respuesta = cliente.put(
        f"/documentos/{documento_id}/partes/1?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers=encabezados,
        content=b"x",
    )
    etag = respuesta.json()["etag"]
    respuesta = cliente.post(
        f"/documentos/{documento_id}/completar?upload_id={upload_id}&llave_almacenamiento={llave}",
        headers=encabezados,
        json={
            "partes": [{"numero_parte": 1, "etag": etag}],
            "tipo_revision": "contable",
            "periodo_cierre": "2026-01",
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    return documento_id, respuesta.json()["analisis_id"]


def test_puede_decidir_segun_rol_y_segregacion_de_funciones(cliente: TestClient) -> None:
    token_analista = _token(cliente, "analista@local")
    _documento_id, analisis_id = _crear_analisis_via_api(cliente, token_analista)

    # Quien cargó el documento (analista) nunca puede decidir, aunque haya
    # otro analista sin ese conflicto tampoco (no tiene el rol requerido).
    respuesta = cliente.get(
        f"/analisis/{analisis_id}", headers={"Authorization": f"Bearer {token_analista}"}
    )
    assert respuesta.json()["puede_decidir"] is False

    token_revisor = _token(cliente, "revisor@local")
    respuesta = cliente.get(
        f"/analisis/{analisis_id}", headers={"Authorization": f"Bearer {token_revisor}"}
    )
    assert respuesta.json()["puede_decidir"] is True


def test_tiene_version_corregida_solo_si_existe_una_version_marcada(
    cliente: TestClient, sesion_bd
) -> None:
    token_analista = _token(cliente, "analista@local")
    documento_id, analisis_id = _crear_analisis_via_api(cliente, token_analista)

    respuesta = cliente.get(
        f"/analisis/{analisis_id}", headers={"Authorization": f"Bearer {token_analista}"}
    )
    assert respuesta.json()["tiene_version_corregida"] is False

    sesion_bd.add(
        VersionDocumento(
            documento_id=uuid.UUID(documento_id),
            numero_version=2,
            ruta_almacenamiento="area/doc/cierre.marcado.xlsx",
            es_corregida=True,
            fecha_creacion=datetime.now(UTC),
        )
    )
    sesion_bd.commit()

    respuesta = cliente.get(
        f"/analisis/{analisis_id}", headers={"Authorization": f"Bearer {token_analista}"}
    )
    assert respuesta.json()["tiene_version_corregida"] is True


def test_descargar_version_corregida(cliente: TestClient, sesion_bd, cliente_s3_bucket) -> None:
    token_analista = _token(cliente, "analista@local")
    documento_id, _analisis_id = _crear_analisis_via_api(cliente, token_analista)

    llave_corregida = "area/doc/cierre.marcado.xlsx"
    contenido_marcado = b"contenido de un excel marcado, de prueba"
    cliente_s3_bucket.put_object(Bucket="documentos", Key=llave_corregida, Body=contenido_marcado)
    sesion_bd.add(
        VersionDocumento(
            documento_id=uuid.UUID(documento_id),
            numero_version=2,
            ruta_almacenamiento=llave_corregida,
            es_corregida=True,
            fecha_creacion=datetime.now(UTC),
        )
    )
    sesion_bd.commit()

    respuesta = cliente.get(
        f"/documentos/{documento_id}/version-corregida",
        headers={"Authorization": f"Bearer {token_analista}"},
    )
    assert respuesta.status_code == 200
    assert respuesta.content == contenido_marcado
    assert "cierre.marcado.xlsx" in respuesta.headers["content-disposition"]


def test_descargar_version_corregida_404_si_no_existe(cliente: TestClient) -> None:
    token_analista = _token(cliente, "analista@local")
    documento_id, _analisis_id = _crear_analisis_via_api(cliente, token_analista)

    respuesta = cliente.get(
        f"/documentos/{documento_id}/version-corregida",
        headers={"Authorization": f"Bearer {token_analista}"},
    )
    assert respuesta.status_code == 404
