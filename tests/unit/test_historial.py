"""Pruebas de GET /historial (P-12, Bloque 3, HU-21): historial de análisis
con alcance (propio/área/todas según permiso), filtros y paginación --
incluye duración y número de hallazgos por análisis.
"""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("API_SECRET_KEY", "clave-de-prueba")

from api import main  # noqa: E402
from comun.modelos import Analisis, Area, Documento, Hallazgo, TipoRevision, Usuario  # noqa: E402


@pytest.fixture()
def cliente(sesion_bd):
    main.app.dependency_overrides[main.obtener_sesion] = lambda: sesion_bd
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


def _token(cliente: TestClient, email: str, password: str = "cambiar123") -> str:
    respuesta = cliente.post("/auth/login", json={"email": email, "password": password})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["access_token"]


def _tipo_revision(sesion_bd, nombre: str = "contable") -> TipoRevision:
    tipo = sesion_bd.query(TipoRevision).filter_by(nombre=nombre).one_or_none()
    if tipo is None:
        tipo = TipoRevision(nombre=nombre)
        sesion_bd.add(tipo)
        sesion_bd.flush()
    return tipo


def _crear_analisis(
    sesion_bd,
    *,
    usuario: Usuario,
    area: Area | None = None,
    tipo_revision_nombre: str = "contable",
    estado_documento: str = "con_hallazgos",
    fecha_inicio: datetime | None = None,
    fecha_fin: datetime | None = None,
    nombre_documento: str = "cierre.xlsx",
    numero_hallazgos: int = 0,
) -> Analisis:
    area = area or sesion_bd.get(Area, usuario.area_id)
    documento = Documento(
        nombre_original=nombre_documento,
        tipo_archivo="xlsx",
        tamano_bytes=100,
        area_id=area.id,
        usuario_carga_id=usuario.id,
        fecha_carga=datetime.now(UTC),
        fecha_expiracion=datetime.now(UTC).date(),
        estado=estado_documento,
    )
    sesion_bd.add(documento)
    sesion_bd.flush()

    analisis = Analisis(
        documento_id=documento.id,
        tipo_revision_id=_tipo_revision(sesion_bd, tipo_revision_nombre).id,
        usuario_id=usuario.id,
        fecha_inicio=fecha_inicio or datetime.now(UTC),
        fecha_fin=fecha_fin,
        estado="completado",
    )
    sesion_bd.add(analisis)
    sesion_bd.flush()

    for _ in range(numero_hallazgos):
        sesion_bd.add(
            Hallazgo(
                analisis_id=analisis.id,
                version_documento_id=uuid.uuid4(),
                severidad="alta",
                ubicacion="Partidas!A1",
                descripcion="hallazgo de prueba",
                estado="pendiente",
            )
        )
    sesion_bd.commit()
    return analisis


def test_historial_alcance_propio_por_defecto_solo_trae_lo_mio(cliente, sesion_bd) -> None:
    analista = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    revisor = sesion_bd.query(Usuario).filter_by(email="revisor@local").one()
    propio = _crear_analisis(sesion_bd, usuario=analista)
    _crear_analisis(sesion_bd, usuario=revisor)

    token = _token(cliente, "analista@local")
    respuesta = cliente.get("/historial", headers={"Authorization": f"Bearer {token}"})
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 1
    assert cuerpo["resultados"][0]["id"] == str(propio.id)


def test_historial_rechaza_alcance_invalido(cliente) -> None:
    token = _token(cliente, "analista@local")
    respuesta = cliente.get(
        "/historial", headers={"Authorization": f"Bearer {token}"}, params={"alcance": "otro"}
    )
    assert respuesta.status_code == 422


def test_historial_rechaza_alcance_sin_el_permiso(cliente) -> None:
    # Analista no tiene historial:todas (ver comun/permisos.py).
    token = _token(cliente, "analista@local")
    respuesta = cliente.get(
        "/historial", headers={"Authorization": f"Bearer {token}"}, params={"alcance": "todas"}
    )
    assert respuesta.status_code == 403


def test_historial_alcance_area_ve_los_analisis_de_toda_el_area(cliente, sesion_bd) -> None:
    analista = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    revisor = sesion_bd.query(Usuario).filter_by(email="revisor@local").one()
    _crear_analisis(sesion_bd, usuario=analista)
    _crear_analisis(sesion_bd, usuario=revisor)

    token = _token(cliente, "analista@local")
    respuesta = cliente.get(
        "/historial", headers={"Authorization": f"Bearer {token}"}, params={"alcance": "area"}
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["total"] == 2


def test_historial_alcance_area_no_ve_otra_area(cliente, sesion_bd) -> None:
    analista = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    otra_area = Area(nombre="Tesorería")
    sesion_bd.add(otra_area)
    sesion_bd.flush()
    _crear_analisis(sesion_bd, usuario=analista)
    _crear_analisis(sesion_bd, usuario=analista, area=otra_area, nombre_documento="otra-area.xlsx")

    token = _token(cliente, "analista@local")
    respuesta = cliente.get(
        "/historial", headers={"Authorization": f"Bearer {token}"}, params={"alcance": "area"}
    )
    assert respuesta.json()["total"] == 1


def test_historial_alcance_todas_solo_administrador_y_auditor(cliente, sesion_bd) -> None:
    analista = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    otra_area = Area(nombre="Tesorería")
    sesion_bd.add(otra_area)
    sesion_bd.flush()
    _crear_analisis(sesion_bd, usuario=analista)
    _crear_analisis(sesion_bd, usuario=analista, area=otra_area, nombre_documento="otra-area.xlsx")

    for email in ("administrador@local", "auditor@local"):
        token = _token(cliente, email)
        respuesta = cliente.get(
            "/historial", headers={"Authorization": f"Bearer {token}"}, params={"alcance": "todas"}
        )
        assert respuesta.status_code == 200, email
        assert respuesta.json()["total"] == 2, email


def test_historial_todas_se_puede_acotar_por_area_id(cliente, sesion_bd) -> None:
    analista = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    otra_area = Area(nombre="Tesorería")
    sesion_bd.add(otra_area)
    sesion_bd.flush()
    _crear_analisis(sesion_bd, usuario=analista)
    _crear_analisis(sesion_bd, usuario=analista, area=otra_area, nombre_documento="otra-area.xlsx")

    token = _token(cliente, "administrador@local")
    respuesta = cliente.get(
        "/historial",
        headers={"Authorization": f"Bearer {token}"},
        params={"alcance": "todas", "area_id": str(otra_area.id)},
    )
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 1
    assert cuerpo["resultados"][0]["nombre_documento"] == "otra-area.xlsx"


def test_historial_incluye_usuario_duracion_y_numero_hallazgos(cliente, sesion_bd) -> None:
    analista = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    inicio = datetime.now(UTC) - timedelta(minutes=5)
    fin = inicio + timedelta(minutes=2)
    _crear_analisis(sesion_bd, usuario=analista, fecha_inicio=inicio, fecha_fin=fin, numero_hallazgos=3)

    token = _token(cliente, "analista@local")
    respuesta = cliente.get("/historial", headers={"Authorization": f"Bearer {token}"})
    item = respuesta.json()["resultados"][0]
    assert item["usuario_email"] == "analista@local"
    assert item["area_nombre"] == "Contabilidad"
    assert item["numero_hallazgos"] == 3
    assert item["duracion_segundos"] == pytest.approx(120.0)


def test_historial_analisis_sin_fecha_fin_no_tiene_duracion(cliente, sesion_bd) -> None:
    analista = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    _crear_analisis(sesion_bd, usuario=analista, fecha_fin=None)

    token = _token(cliente, "analista@local")
    respuesta = cliente.get("/historial", headers={"Authorization": f"Bearer {token}"})
    assert respuesta.json()["resultados"][0]["duracion_segundos"] is None


def test_historial_filtra_por_tipo_revision_estado_y_archivo(cliente, sesion_bd) -> None:
    analista = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    _crear_analisis(
        sesion_bd,
        usuario=analista,
        tipo_revision_nombre="contable",
        estado_documento="con_hallazgos",
        nombre_documento="cierre-mayo.xlsx",
    )
    _crear_analisis(
        sesion_bd,
        usuario=analista,
        tipo_revision_nombre="ortografia",
        estado_documento="aprobado",
        nombre_documento="memo.docx",
    )

    token = _token(cliente, "analista@local")
    encabezados = {"Authorization": f"Bearer {token}"}

    respuesta = cliente.get("/historial", headers=encabezados, params={"tipo_revision": "contable"})
    assert respuesta.json()["total"] == 1

    respuesta = cliente.get("/historial", headers=encabezados, params={"estado": "aprobado"})
    assert respuesta.json()["total"] == 1
    assert respuesta.json()["resultados"][0]["nombre_documento"] == "memo.docx"

    respuesta = cliente.get("/historial", headers=encabezados, params={"archivo": "cierre"})
    assert respuesta.json()["total"] == 1
    assert respuesta.json()["resultados"][0]["nombre_documento"] == "cierre-mayo.xlsx"


def test_historial_filtra_por_rango_de_fechas(cliente, sesion_bd) -> None:
    analista = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    hoy = datetime.now(UTC)
    _crear_analisis(sesion_bd, usuario=analista, fecha_inicio=hoy)
    _crear_analisis(sesion_bd, usuario=analista, fecha_inicio=hoy - timedelta(days=10))

    token = _token(cliente, "analista@local")
    respuesta = cliente.get(
        "/historial",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "desde": (hoy.date() - timedelta(days=1)).isoformat(),
            "hasta": hoy.date().isoformat(),
        },
    )
    assert respuesta.json()["total"] == 1


def test_historial_pagina(cliente, sesion_bd) -> None:
    analista = sesion_bd.query(Usuario).filter_by(email="analista@local").one()
    for i in range(5):
        _crear_analisis(
            sesion_bd,
            usuario=analista,
            nombre_documento=f"doc-{i}.xlsx",
            fecha_inicio=datetime.now(UTC) - timedelta(minutes=i),
        )

    token = _token(cliente, "analista@local")
    encabezados = {"Authorization": f"Bearer {token}"}

    respuesta = cliente.get(
        "/historial", headers=encabezados, params={"pagina": 1, "tamano_pagina": 2}
    )
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 5
    assert len(cuerpo["resultados"]) == 2
    assert cuerpo["resultados"][0]["nombre_documento"] == "doc-0.xlsx"

    respuesta = cliente.get(
        "/historial", headers=encabezados, params={"pagina": 3, "tamano_pagina": 2}
    )
    cuerpo = respuesta.json()
    assert len(cuerpo["resultados"]) == 1
    assert cuerpo["resultados"][0]["nombre_documento"] == "doc-4.xlsx"


def test_historial_rechaza_pagina_o_tamano_invalidos(cliente) -> None:
    token = _token(cliente, "analista@local")
    encabezados = {"Authorization": f"Bearer {token}"}
    assert cliente.get("/historial", headers=encabezados, params={"pagina": 0}).status_code == 422
    assert (
        cliente.get("/historial", headers=encabezados, params={"tamano_pagina": 101}).status_code
        == 422
    )
