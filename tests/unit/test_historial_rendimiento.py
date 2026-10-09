"""Prueba de rendimiento de GET /historial (P-12, Bloque 5): con 10,000
análisis sintéticos, debe responder en <= 1 s -- la razón de ser de los
índices sembrados en el Bloque 1 (ix_analisis_fecha_inicio,
ix_documento_usuario_carga_area, ver comun/modelos.py).
"""

import os
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert

os.environ.setdefault("API_SECRET_KEY", "clave-de-prueba")

from api import main  # noqa: E402
from comun.modelos import Analisis, Documento, TipoRevision, Usuario  # noqa: E402

TOTAL_ANALISIS_SINTETICOS = 10_000
LIMITE_SEGUNDOS = 1.0


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


def _sembrar_analisis_sinteticos(sesion_bd, *, usuario: Usuario, total: int) -> None:
    """Inserción masiva (SQLAlchemy Core, no ORM) -- con `total`=10,000 filas,
    crear los objetos uno por uno con la sesión de ORM sería el propio cuello
    de botella que esta prueba busca medir en el endpoint, no en el setup."""
    tipo_revision = sesion_bd.query(TipoRevision).filter_by(nombre="contable").one_or_none()
    if tipo_revision is None:
        tipo_revision = TipoRevision(nombre="contable")
        sesion_bd.add(tipo_revision)
        sesion_bd.flush()

    ahora = datetime.now(UTC)
    documentos = []
    analisis_filas = []
    for i in range(total):
        documento_id = uuid.uuid4()
        documentos.append(
            {
                "id": documento_id,
                "nombre_original": f"doc-sintetico-{i}.xlsx",
                "tipo_archivo": "xlsx",
                "tamano_bytes": 100,
                "area_id": usuario.area_id,
                "usuario_carga_id": usuario.id,
                "fecha_carga": ahora,
                "fecha_expiracion": ahora.date(),
                "estado": "con_hallazgos",
            }
        )
        inicio = ahora - timedelta(seconds=i)
        analisis_filas.append(
            {
                "id": uuid.uuid4(),
                "documento_id": documento_id,
                "tipo_revision_id": tipo_revision.id,
                "usuario_id": usuario.id,
                "fecha_inicio": inicio,
                "fecha_fin": inicio + timedelta(minutes=1),
                "estado": "completado",
            }
        )

    sesion_bd.execute(insert(Documento), documentos)
    sesion_bd.execute(insert(Analisis), analisis_filas)
    sesion_bd.commit()


def test_historial_responde_en_un_segundo_con_diez_mil_analisis(
    cliente: TestClient, sesion_bd
) -> None:
    administrador = sesion_bd.query(Usuario).filter_by(email="administrador@local").one()
    _sembrar_analisis_sinteticos(
        sesion_bd, usuario=administrador, total=TOTAL_ANALISIS_SINTETICOS
    )

    token = _token(cliente, "administrador@local")
    inicio = time.perf_counter()
    respuesta = cliente.get(
        "/historial",
        headers={"Authorization": f"Bearer {token}"},
        params={"alcance": "todas", "tamano_pagina": 20},
    )
    duracion = time.perf_counter() - inicio

    assert respuesta.status_code == 200
    assert respuesta.json()["total"] == TOTAL_ANALISIS_SINTETICOS
    assert duracion <= LIMITE_SEGUNDOS, (
        f"GET /historial tardó {duracion:.3f} s con {TOTAL_ANALISIS_SINTETICOS} "
        f"análisis (límite {LIMITE_SEGUNDOS} s)"
    )
