"""Pruebas de los endpoints de la pantalla del curador (RF-16, RF-19,
CU-08, Bloque K5): fuentes (crear/vista previa/aprobar/marcar obsoleta),
glosario y plantilla -- contra la API real (TestClient), no las funciones
de dominio sueltas (esas ya están cubiertas en tests/unit/test_curaduria_*).
"""

import os
import uuid
from pathlib import Path

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from qdrant_client import QdrantClient

os.environ.setdefault("API_SECRET_KEY", "clave-de-prueba")

from api import main  # noqa: E402
from comun.modelos import Bitacora, FuenteConocimiento, Glosario  # noqa: E402
from rag.cliente_embeddings import DIMENSION_BGE_M3  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
RUTA_PDF_EJEMPLO = RAIZ / "kb" / "plantillas" / "ejemplos" / "POL-001_Politica_Cierre_EJEMPLO.pdf"
RUTA_PLANTILLA_REAL = RAIZ / "kb" / "plantillas" / "Plantilla_Base_Conocimiento_SFC.xlsx"

COLECCION_PRUEBA = "kb_prueba_k5"


def _embedding_falso(_texto: str) -> list[float]:
    # El endpoint /curaduria/fuentes/{id}/aprobar crea la colección con
    # DIMENSION_BGE_M3 (1024, confirmado contra el Ollama real) -- el vector
    # de prueba debe tener el mismo tamaño o Qdrant lo rechaza.
    return [0.1] * DIMENSION_BGE_M3


@pytest.fixture()
def cliente(sesion_bd):
    with mock_aws():
        cliente_s3 = boto3.client("s3", region_name="us-east-1")
        cliente_s3.create_bucket(Bucket="documentos")
        cliente_s3.create_bucket(Bucket="conocimiento")

        cliente_qdrant = QdrantClient(":memory:")

        main.app.dependency_overrides[main.obtener_sesion] = lambda: sesion_bd
        main.app.dependency_overrides[main.obtener_cliente_almacenamiento] = lambda: cliente_s3
        main.app.dependency_overrides[main.obtener_cliente_qdrant] = lambda: cliente_qdrant
        main.app.dependency_overrides[main.obtener_funcion_embedding] = lambda: _embedding_falso
        main.app.dependency_overrides[main.obtener_coleccion_kb] = lambda: COLECCION_PRUEBA

        with TestClient(main.app) as test_client:
            yield test_client, cliente_qdrant

        main.app.dependency_overrides.clear()


def _token(cliente: TestClient, email: str, password: str = "cambiar123") -> str:
    respuesta = cliente.post("/auth/login", json={"email": email, "password": password})
    assert respuesta.status_code == 200
    return respuesta.json()["access_token"]


def _encabezados(cliente: TestClient, email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(cliente, email)}"}


def _crear_fuente(
    cliente: TestClient, encabezados: dict[str, str], *, ruta_archivo: Path = RUTA_PDF_EJEMPLO
) -> dict:
    respuesta = cliente.post(
        "/curaduria/fuentes",
        headers=encabezados,
        data={
            "fuente_id": "POL-001",
            "titulo": "Política de cierre contable",
            "tipo": "política (Word)",
            "version": "2026-01",
            "vigente_desde": "2026-01-15",
            "dueno": "Jefatura de Contabilidad",
        },
        files={"archivo": (ruta_archivo.name, ruta_archivo.read_bytes(), "application/pdf")},
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


# --- fuentes: alcance por área ------------------------------------------------


def test_listar_fuentes_curaduria_solo_del_area_del_curador(cliente) -> None:
    test_client, _qdrant = cliente
    encabezados_curador = _encabezados(test_client, "curador@local")
    fuente = _crear_fuente(test_client, encabezados_curador)
    assert fuente["estado"] == "borrador"

    respuesta = test_client.get("/curaduria/fuentes", headers=encabezados_curador)
    assert respuesta.status_code == 200
    assert {f["fuente_id"] for f in respuesta.json()} == {"POL-001"}


def test_analista_no_puede_acceder_a_curaduria(cliente) -> None:
    test_client, _qdrant = cliente
    encabezados = _encabezados(test_client, "analista@local")

    assert test_client.get("/curaduria/fuentes", headers=encabezados).status_code == 403
    assert test_client.get("/curaduria/glosario", headers=encabezados).status_code == 403


def test_administrador_solo_lectura_no_puede_crear_fuente(cliente) -> None:
    test_client, _qdrant = cliente
    encabezados = _encabezados(test_client, "administrador@local")

    respuesta = test_client.post(
        "/curaduria/fuentes",
        headers=encabezados,
        data={
            "fuente_id": "POL-002",
            "titulo": "x",
            "tipo": "política (Word)",
            "version": "1.0",
            "vigente_desde": "2026-01-01",
            "dueno": "x",
        },
        files={"archivo": ("x.pdf", b"contenido", "application/pdf")},
    )
    assert respuesta.status_code == 403


def test_administrador_ve_fuentes_de_todas_las_areas_pero_solo_lectura(cliente) -> None:
    test_client, _qdrant = cliente
    _crear_fuente(test_client, _encabezados(test_client, "curador@local"))

    respuesta = test_client.get(
        "/curaduria/fuentes", headers=_encabezados(test_client, "administrador@local")
    )
    assert respuesta.status_code == 200
    assert len(respuesta.json()) == 1


# --- fuentes: ciclo de vida completo ------------------------------------------


def test_crear_fuente_persiste_como_borrador_y_registra_bitacora(cliente, sesion_bd) -> None:
    test_client, _qdrant = cliente
    fuente = _crear_fuente(test_client, _encabezados(test_client, "curador@local"))

    assert fuente["estado"] == "borrador"
    assert fuente["tipo"] == "regla_interna"  # clasificado desde "política (Word)"
    assert fuente["sha256"] is not None

    bitacora = sesion_bd.query(Bitacora).filter_by(accion="fuente_cargada").one()
    assert "POL-001" in bitacora.detalle


def test_vista_previa_extrae_fragmentos_sin_persistirlos(cliente, sesion_bd) -> None:
    test_client, _qdrant = cliente
    encabezados = _encabezados(test_client, "curador@local")
    fuente = _crear_fuente(test_client, encabezados)

    respuesta = test_client.get(
        f"/curaduria/fuentes/{fuente['id']}/vista-previa", headers=encabezados
    )
    assert respuesta.status_code == 200
    fragmentos = respuesta.json()["fragmentos"]
    assert any(f["seccion"] == "§3" for f in fragmentos)

    from comun.modelos import Fragmento

    assert sesion_bd.query(Fragmento).count() == 0  # no se indexó nada todavía


def test_aprobar_fuente_indexa_y_la_deja_vigente(cliente, sesion_bd) -> None:
    test_client, cliente_qdrant = cliente
    encabezados = _encabezados(test_client, "curador@local")
    fuente = _crear_fuente(test_client, encabezados)

    respuesta = test_client.post(
        f"/curaduria/fuentes/{fuente['id']}/aprobar", headers=encabezados
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["fragmentos_indexados"] == 7  # título + 6 secciones (§1..§6)
    assert cuerpo["version_anterior_obsoleta"] is False

    fuente_bd = sesion_bd.get(FuenteConocimiento, uuid.UUID(fuente["id"]))
    assert fuente_bd.estado == "vigente"
    assert fuente_bd.aprobado_por is not None

    assert cliente_qdrant.count(collection_name=COLECCION_PRUEBA).count == 7
    assert sesion_bd.query(Bitacora).filter_by(accion="fuente_aprobada").count() == 1
    assert sesion_bd.query(Bitacora).filter_by(accion="fuente_indexada").count() == 1


def test_aprobar_una_segunda_version_obsoletea_la_primera(cliente, sesion_bd) -> None:
    test_client, cliente_qdrant = cliente
    encabezados = _encabezados(test_client, "curador@local")

    v1 = _crear_fuente(test_client, encabezados)
    test_client.post(f"/curaduria/fuentes/{v1['id']}/aprobar", headers=encabezados)

    respuesta_v2 = test_client.post(
        "/curaduria/fuentes",
        headers=encabezados,
        data={
            "fuente_id": "POL-001",
            "titulo": "Política de cierre contable",
            "tipo": "política (Word)",
            "version": "2026-02",
            "vigente_desde": "2026-02-01",
            "dueno": "Jefatura de Contabilidad",
        },
        files={
            "archivo": (
                RUTA_PDF_EJEMPLO.name,
                RUTA_PDF_EJEMPLO.read_bytes(),
                "application/pdf",
            )
        },
    )
    v2 = respuesta_v2.json()

    respuesta = test_client.post(f"/curaduria/fuentes/{v2['id']}/aprobar", headers=encabezados)
    assert respuesta.status_code == 200
    assert respuesta.json()["version_anterior_obsoleta"] is True

    assert sesion_bd.get(FuenteConocimiento, uuid.UUID(v1["id"])).estado == "obsoleta"
    assert sesion_bd.get(FuenteConocimiento, uuid.UUID(v2["id"])).estado == "vigente"
    # v1 y v2 comparten fuente_id (POL-001) -- desactivar_fragmentos_de_fuente
    # filtra por ese fuente_id de negocio, así que el endpoint debe desactivar
    # los puntos de v1 ANTES de indexar los de v2 (no después), o si no los
    # puntos recién indexados de v2 quedarían marcados "obsoleta" también
    # (RF-16/PP-08: solo la versión vigente debe ser buscable).
    assert cliente_qdrant.count(collection_name=COLECCION_PRUEBA).count == 14

    from comun.modelos import Fragmento

    fragmentos_v2 = sesion_bd.query(Fragmento).filter_by(fuente_id=uuid.UUID(v2["id"])).all()
    assert len(fragmentos_v2) == 7
    puntos_v2 = cliente_qdrant.retrieve(
        collection_name=COLECCION_PRUEBA,
        ids=[f.referencia_vector for f in fragmentos_v2],
        with_payload=True,
    )
    assert all(p.payload["estado"] == "vigente" for p in puntos_v2)

    fragmentos_v1 = sesion_bd.query(Fragmento).filter_by(fuente_id=uuid.UUID(v1["id"])).all()
    puntos_v1 = cliente_qdrant.retrieve(
        collection_name=COLECCION_PRUEBA,
        ids=[f.referencia_vector for f in fragmentos_v1],
        with_payload=True,
    )
    assert all(p.payload["estado"] == "obsoleta" for p in puntos_v1)


def test_aprobar_fuente_que_no_esta_en_borrador_da_409(cliente) -> None:
    test_client, _qdrant = cliente
    encabezados = _encabezados(test_client, "curador@local")
    fuente = _crear_fuente(test_client, encabezados)
    test_client.post(f"/curaduria/fuentes/{fuente['id']}/aprobar", headers=encabezados)

    respuesta = test_client.post(f"/curaduria/fuentes/{fuente['id']}/aprobar", headers=encabezados)
    assert respuesta.status_code == 409


def test_marcar_obsoleta_desactiva_los_fragmentos(cliente, sesion_bd) -> None:
    test_client, cliente_qdrant = cliente
    encabezados = _encabezados(test_client, "curador@local")
    fuente = _crear_fuente(test_client, encabezados)
    test_client.post(f"/curaduria/fuentes/{fuente['id']}/aprobar", headers=encabezados)

    respuesta = test_client.post(
        f"/curaduria/fuentes/{fuente['id']}/marcar-obsoleta", headers=encabezados
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "obsoleta"

    from comun.modelos import Fragmento

    fila = sesion_bd.query(Fragmento).filter_by(fuente_id=uuid.UUID(fuente["id"])).first()
    punto = cliente_qdrant.retrieve(
        collection_name=COLECCION_PRUEBA, ids=[fila.referencia_vector], with_payload=True
    )[0]
    assert punto.payload["estado"] == "obsoleta"


def test_marcar_obsoleta_un_borrador_da_409(cliente) -> None:
    test_client, _qdrant = cliente
    encabezados = _encabezados(test_client, "curador@local")
    fuente = _crear_fuente(test_client, encabezados)

    respuesta = test_client.post(
        f"/curaduria/fuentes/{fuente['id']}/marcar-obsoleta", headers=encabezados
    )
    assert respuesta.status_code == 409


def test_curador_no_puede_gestionar_fuente_de_otra_area(cliente, sesion_bd) -> None:
    """Simula una fuente que quedó (o se creó a mano) en otra área: el
    curador de "Contabilidad" no puede aprobarla ni verla en su vista
    previa, aunque conozca su id."""
    test_client, _qdrant = cliente
    encabezados = _encabezados(test_client, "curador@local")
    fuente = _crear_fuente(test_client, encabezados)

    from comun.modelos import Area

    otra_area = Area(nombre="Impuestos")
    sesion_bd.add(otra_area)
    sesion_bd.flush()
    fila = sesion_bd.get(FuenteConocimiento, uuid.UUID(fuente["id"]))
    fila.area_id = otra_area.id
    sesion_bd.commit()

    respuesta_listado = test_client.get("/curaduria/fuentes", headers=encabezados)
    assert fuente["id"] not in {f["id"] for f in respuesta_listado.json()}

    respuesta_aprobar = test_client.post(
        f"/curaduria/fuentes/{fuente['id']}/aprobar", headers=encabezados
    )
    assert respuesta_aprobar.status_code == 403


# --- glosario ------------------------------------------------------------------


def test_editor_de_glosario_crear_listar_y_eliminar(cliente, sesion_bd) -> None:
    test_client, _qdrant = cliente
    encabezados = _encabezados(test_client, "curador@local")

    respuesta = test_client.post(
        "/curaduria/glosario",
        headers=encabezados,
        json={"termino": "DTE", "definicion": "Documento Tributario Electrónico"},
    )
    assert respuesta.status_code == 200
    termino = respuesta.json()

    respuesta = test_client.get("/curaduria/glosario", headers=encabezados)
    assert any(t["termino"] == "DTE" for t in respuesta.json())

    respuesta = test_client.delete(
        f"/curaduria/glosario/{termino['id']}", headers=encabezados
    )
    assert respuesta.status_code == 204
    assert sesion_bd.get(Glosario, uuid.UUID(termino["id"])) is None
    assert sesion_bd.query(Bitacora).filter_by(accion="glosario_eliminado").count() == 1


def test_analista_no_puede_crear_termino_de_glosario(cliente) -> None:
    test_client, _qdrant = cliente
    respuesta = test_client.post(
        "/curaduria/glosario",
        headers=_encabezados(test_client, "analista@local"),
        json={"termino": "X", "definicion": "Y"},
    )
    assert respuesta.status_code == 403


# --- plantilla -------------------------------------------------------------


def test_validar_plantilla_real_no_persiste_nada(cliente, sesion_bd) -> None:
    test_client, _qdrant = cliente
    encabezados = _encabezados(test_client, "curador@local")

    respuesta = test_client.post(
        "/curaduria/plantilla/validar",
        headers=encabezados,
        files={
            "archivo": (
                RUTA_PLANTILLA_REAL.name,
                RUTA_PLANTILLA_REAL.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["es_valido"] is True
    assert cuerpo["resumen"] == {
        "fuentes": 8, "cuentas": 42, "reglas": 14, "glosario": 16, "checklist": 12
    }
    assert sesion_bd.query(FuenteConocimiento).count() == 0


def test_importar_plantilla_real_persiste_todo_como_borrador(cliente, sesion_bd) -> None:
    test_client, _qdrant = cliente
    encabezados = _encabezados(test_client, "curador@local")

    respuesta = test_client.post(
        "/curaduria/plantilla/importar",
        headers=encabezados,
        files={
            "archivo": (
                RUTA_PLANTILLA_REAL.name,
                RUTA_PLANTILLA_REAL.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["es_valido"] is True
    assert cuerpo["cargado"]["fuentes"] == 8

    fuentes = sesion_bd.query(FuenteConocimiento).all()
    assert len(fuentes) == 8
    assert all(f.estado == "borrador" for f in fuentes)
    assert sesion_bd.query(Bitacora).filter_by(accion="plantilla_importada").count() == 1


def test_importar_plantilla_con_errores_no_persiste_nada(cliente, sesion_bd) -> None:
    """Bloque K7: 5 tipos de error DISTINTOS sembrados a la vez, uno por
    hoja (estado inválido, código duplicado, fuente_id de regla
    inexistente, fecha inválida, columna "n" no numérica) -- mismos casos
    que tests/unit/test_curaduria_plantilla.py::
    test_leer_plantilla_con_errores_sembrados_en_las_cinco_hojas_a_la_vez,
    acá contra el endpoint real de la API (lo que de verdad usa la
    pantalla del curador)."""
    import io

    from openpyxl import Workbook

    def _hoja(wb: Workbook, nombre: str, columnas: tuple, filas: list[tuple]) -> None:
        ws = wb.create_sheet(nombre)
        ws.append(("t",))
        ws.append(("d",))
        ws.append(())
        ws.append(columnas)
        for fila in filas:
            ws.append(fila)

    wb = Workbook()
    wb.remove(wb.active)
    _hoja(
        wb,
        "Inventario de fuentes",
        ("fuente_id", "titulo", "tipo", "version", "vigente_desde", "estado", "dueno_area",
         "archivo_entregado", "observaciones"),
        [
            ("POL-001", "Política de cierre", "política (Word)", "1.0", "2026-01-01",
             "publicado", "x", "a.docx", None),  # estado inválido
            ("CAT-001", "Catálogo de cuentas", "catálogo (Excel)", "1.0", "2026-01-01",
             "vigente", "x", "b.xlsx", None),
        ],
    )
    _hoja(
        wb,
        "Catálogo de cuentas",
        ("codigo", "nombre", "tipo", "naturaleza", "acepta_movimiento", "notas"),
        [
            ("1101", "Caja general", "activo", "deudora", "Sí", None),
            ("1101", "Caja general (dup)", "activo", "deudora", "Sí", None),  # código duplicado
        ],
    )
    _hoja(
        wb,
        "Reglas contables",
        ("id_regla", "descripcion", "area", "tipo_documento", "severidad", "moneda",
         "fuente_id", "estado_validacion"),
        [("RN-99", "Regla nueva", "Contabilidad", "Excel", "alta", "Q", "ZZZ-999", "Sí")],
    )  # fuente_id de regla inexistente en el inventario
    _hoja(
        wb,
        "Glosario",
        ("termino", "definicion", "area", "fuente_id", "vigente_desde"),
        [("XYZ", "Definición", "General", "CAT-001", "no-es-fecha")],
    )  # fecha inválida
    _hoja(
        wb,
        "Checklist de cierre",
        ("n", "actividad", "responsable", "plazo", "evidencia_requerida"),
        [("no-es-numero", "Actividad", "Tesorería", "Día 2", "Evidencia")],
    )  # columna "n" no numérica
    buffer = io.BytesIO()
    wb.save(buffer)

    test_client, _qdrant = cliente
    respuesta = test_client.post(
        "/curaduria/plantilla/importar",
        headers=_encabezados(test_client, "curador@local"),
        files={"archivo": ("mala.xlsx", buffer.getvalue(), "application/octet-stream")},
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["es_valido"] is False
    assert cuerpo["cargado"] is None

    hojas_con_error = {e["hoja"] for e in cuerpo["errores"]}
    assert hojas_con_error == {
        "Inventario de fuentes",
        "Catálogo de cuentas",
        "Reglas contables",
        "Glosario",
        "Checklist de cierre",
    }
    assert sesion_bd.query(FuenteConocimiento).count() == 0
