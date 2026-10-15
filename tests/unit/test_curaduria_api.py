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
from comun.almacenamiento import descargar_objeto  # noqa: E402
from comun.modelos import Bitacora, FuenteConocimiento, Glosario, UsoLlm  # noqa: E402
from comun.uso_llm import envolver_funcion_embedding_inyectada  # noqa: E402
from curaduria.aprobacion import procesar_indexacion  # noqa: E402
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

        def _encolador_sincrono(fuente_id: str, usuario_id: str) -> str:
            # En producción corre en el worker (cola "indexacion"); acá, en el mismo proceso.
            fuente = sesion_bd.get(FuenteConocimiento, uuid.UUID(fuente_id))
            procesar_indexacion(
                sesion_bd,
                cliente_qdrant,
                fuente_id=fuente.id,
                usuario_id=uuid.UUID(usuario_id),
                obtener_contenido=lambda: descargar_objeto(
                    cliente_s3, "conocimiento", fuente.archivo
                ),
                funcion_embedding=envolver_funcion_embedding_inyectada(
                    _embedding_falso,
                    sesion=sesion_bd,
                    usuario_id=uuid.UUID(usuario_id),
                    area_id=fuente.area_id,
                    analisis_id=None,
                    caso_uso="embeddings_kb",
                ),
                dimension=DIMENSION_BGE_M3,
                coleccion=COLECCION_PRUEBA,
            )
            return "tarea-falsa"

        main.app.dependency_overrides[main.obtener_encolador_indexacion] = (
            lambda: _encolador_sincrono
        )

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

    respuesta = test_client.post(f"/curaduria/fuentes/{fuente['id']}/aprobar", headers=encabezados)
    assert respuesta.status_code == 202, respuesta.text
    assert respuesta.json()["estado"] == "indexando"  # responde antes de indexar

    fuente_bd = sesion_bd.get(FuenteConocimiento, uuid.UUID(fuente["id"]))
    assert fuente_bd.estado == "vigente"
    assert fuente_bd.aprobado_por is not None

    assert cliente_qdrant.count(collection_name=COLECCION_PRUEBA).count == 7
    assert sesion_bd.query(Bitacora).filter_by(accion="fuente_aprobada").count() == 1
    assert sesion_bd.query(Bitacora).filter_by(accion="fuente_indexada").count() == 1

    # P-13 (Bloque 1, RF-21): una fila de uso por fragmento embebido, aunque
    # funcion_embedding venga de un fake inyectado por Depends.
    usos = sesion_bd.query(UsoLlm).filter_by(caso_uso="embeddings_kb").all()
    assert len(usos) == 7
    assert all(u.resultado == "ok" and u.analisis_id is None for u in usos)


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
    assert respuesta.status_code == 202

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

    respuesta = test_client.delete(f"/curaduria/glosario/{termino['id']}", headers=encabezados)
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
        "fuentes": 8,
        "cuentas": 42,
        "reglas": 14,
        "glosario": 16,
        "checklist": 12,
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
        (
            "fuente_id",
            "titulo",
            "tipo",
            "version",
            "vigente_desde",
            "estado",
            "dueno_area",
            "archivo_entregado",
            "observaciones",
        ),
        [
            (
                "POL-001",
                "Política de cierre",
                "política (Word)",
                "1.0",
                "2026-01-01",
                "publicado",
                "x",
                "a.docx",
                None,
            ),  # estado inválido
            (
                "CAT-001",
                "Catálogo de cuentas",
                "catálogo (Excel)",
                "1.0",
                "2026-01-01",
                "vigente",
                "x",
                "b.xlsx",
                None,
            ),
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
        (
            "id_regla",
            "descripcion",
            "area",
            "tipo_documento",
            "severidad",
            "moneda",
            "fuente_id",
            "estado_validacion",
        ),
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


def test_si_la_cola_no_responde_la_fuente_queda_en_error_indexacion_y_se_puede_reintentar(
    cliente, sesion_bd
) -> None:
    test_client, _qdrant = cliente
    encabezados = _encabezados(test_client, "curador@local")
    fuente = _crear_fuente(test_client, encabezados)
    encolador_sincrono = main.app.dependency_overrides[main.obtener_encolador_indexacion]

    def _cola_caida():
        def _encolar(_fuente_id: str, _usuario_id: str) -> str:
            raise ConnectionError("redis caído")

        return _encolar

    main.app.dependency_overrides[main.obtener_encolador_indexacion] = _cola_caida
    respuesta = test_client.post(f"/curaduria/fuentes/{fuente['id']}/aprobar", headers=encabezados)
    assert respuesta.status_code == 503
    assert "reintente" in respuesta.json()["detail"]

    listado = test_client.get("/curaduria/fuentes", headers=encabezados).json()
    fila = next(f for f in listado if f["id"] == fuente["id"])
    assert fila["estado"] == "error_indexacion"
    assert "cola no disponible" in fila["motivo_error"]
    assert sesion_bd.query(Bitacora).filter_by(accion="fuente_indexacion_fallida").count() == 1

    main.app.dependency_overrides[main.obtener_encolador_indexacion] = encolador_sincrono
    reintento = test_client.post(f"/curaduria/fuentes/{fuente['id']}/aprobar", headers=encabezados)
    assert reintento.status_code == 202
    assert sesion_bd.get(FuenteConocimiento, uuid.UUID(fuente["id"])).estado == "vigente"
    assert sesion_bd.query(Bitacora).filter_by(accion="fuente_indexacion_reintentada").count() == 1


def test_aprobar_una_fuente_que_ya_se_esta_indexando_da_409(cliente, sesion_bd) -> None:
    test_client, _qdrant = cliente
    encabezados = _encabezados(test_client, "curador@local")
    fuente = _crear_fuente(test_client, encabezados)
    sesion_bd.get(FuenteConocimiento, uuid.UUID(fuente["id"])).estado = "indexando"
    sesion_bd.commit()

    respuesta = test_client.post(f"/curaduria/fuentes/{fuente['id']}/aprobar", headers=encabezados)

    assert respuesta.status_code == 409
    assert "ya se está indexando" in respuesta.json()["detail"]


def test_el_listado_expone_el_progreso_de_la_indexacion(cliente, sesion_bd) -> None:
    test_client, _qdrant = cliente
    encabezados = _encabezados(test_client, "curador@local")
    fuente = _crear_fuente(test_client, encabezados)
    fila = sesion_bd.get(FuenteConocimiento, uuid.UUID(fuente["id"]))
    fila.estado, fila.fragmentos_total, fila.fragmentos_procesados = "indexando", 40, 12
    sesion_bd.commit()

    listado = test_client.get("/curaduria/fuentes", headers=encabezados).json()

    item = next(f for f in listado if f["id"] == fuente["id"])
    assert (item["estado"], item["fragmentos_procesados"], item["fragmentos_total"]) == (
        "indexando",
        12,
        40,
    )


# --- Bloque 3.5: unicidad de fuentes ---------------------------------------------------


def _post_fuente(test_client, encabezados, **cambios):
    datos = {
        "fuente_id": "CONTIT-001",
        "titulo": "Redes y Telecomunicaciones",
        "tipo": "política (Word)",
        "version": "1",
        "vigente_desde": "2026-01-15",
        "dueno": "TI",
    }
    datos.update(cambios)
    return test_client.post(
        "/curaduria/fuentes",
        headers=encabezados,
        data=datos,
        files={"archivo": ("doc.pdf", RUTA_PDF_EJEMPLO.read_bytes(), "application/pdf")},
    )


def test_alta_duplicada_se_rechaza_con_409_sin_tocar_el_archivo_existente(
    cliente, sesion_bd
) -> None:
    test_client, _qdrant = cliente
    encabezados = _encabezados(test_client, "curador@local")
    assert _post_fuente(test_client, encabezados).status_code == 200
    s3 = main.app.dependency_overrides[main.obtener_cliente_almacenamiento]()
    antes = s3.list_objects_v2(Bucket="conocimiento")["Contents"]

    respuesta = _post_fuente(test_client, encabezados, titulo="Patrón de diseños")

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == (
        "Ya existe CONTIT-001 versión 1; use otro ID o suba una nueva versión"
    )
    assert sesion_bd.query(FuenteConocimiento).filter_by(fuente_id="CONTIT-001").count() == 1
    despues = s3.list_objects_v2(Bucket="conocimiento")["Contents"]
    assert [(o["Key"], o["ETag"]) for o in despues] == [(o["Key"], o["ETag"]) for o in antes]


def test_nueva_version_del_mismo_documento_se_acepta(cliente, sesion_bd) -> None:
    test_client, _qdrant = cliente
    encabezados = _encabezados(test_client, "curador@local")
    _post_fuente(test_client, encabezados)

    respuesta = _post_fuente(test_client, encabezados, version="2")

    assert respuesta.status_code == 200
    assert respuesta.json()["version"] == "2" and respuesta.json()["advertencias"] is None
    assert sesion_bd.query(FuenteConocimiento).filter_by(fuente_id="CONTIT-001").count() == 2


def test_nueva_version_con_otro_titulo_se_acepta_con_advertencia(cliente) -> None:
    test_client, _qdrant = cliente
    encabezados = _encabezados(test_client, "curador@local")
    _post_fuente(test_client, encabezados)

    respuesta = _post_fuente(test_client, encabezados, version="2", titulo="Patrón de diseños")

    assert respuesta.status_code == 200
    assert "Redes y Telecomunicaciones" in respuesta.json()["advertencias"][0]


def test_nueva_version_con_otro_tipo_se_rechaza(cliente) -> None:
    test_client, _qdrant = cliente
    encabezados = _encabezados(test_client, "curador@local")
    _post_fuente(test_client, encabezados)

    respuesta = _post_fuente(test_client, encabezados, version="2", tipo="normativa (ley)")

    assert respuesta.status_code == 409
    assert "tipo" in respuesta.json()["detail"]


def test_id_de_otra_area_se_rechaza_con_403(cliente, sesion_bd) -> None:
    from datetime import UTC, date, datetime

    from comun.modelos import Area, Usuario

    test_client, _qdrant = cliente
    otra = Area(nombre="Tesorería")
    sesion_bd.add(otra)
    sesion_bd.flush()
    autor = sesion_bd.query(Usuario).first()
    sesion_bd.add(
        FuenteConocimiento(
            fuente_id="CONTIT-001",
            titulo="De otra área",
            tipo="regla_interna",
            prioridad=1,
            version="1",
            vigente_desde=date(2026, 1, 1),
            estado="borrador",
            area_id=otra.id,
            dueno="Tesorería",
            archivo="x/CONTIT-001/1/a.pdf",
            cargado_por=autor.id,
            fecha_carga=datetime.now(UTC),
        )
    )
    sesion_bd.commit()
    encabezados = _encabezados(test_client, "curador@local")

    respuesta = _post_fuente(test_client, encabezados, version="2")

    assert respuesta.status_code == 403
    assert "otra área" in respuesta.json()["detail"]


def test_validar_alta_adelanta_el_veredicto_antes_de_subir_el_archivo(cliente) -> None:
    test_client, _qdrant = cliente
    encabezados = _encabezados(test_client, "curador@local")
    _post_fuente(test_client, encabezados)

    def validar(**c):
        cuerpo = {
            "fuente_id": "CONTIT-001",
            "version": "1",
            "titulo": "Redes y Telecomunicaciones",
            "tipo": "política (Word)",
        }
        cuerpo.update(c)
        return test_client.post("/curaduria/fuentes/validar-alta", headers=encabezados, json=cuerpo)

    duplicada = validar().json()
    assert duplicada["permitido"] is False and duplicada["codigo_http"] == 409
    assert "Ya existe CONTIT-001 versión 1" in duplicada["mensaje"]
    nueva = validar(version="2", titulo="Otro título").json()
    assert nueva["permitido"] and nueva["es_nueva_version"] and len(nueva["advertencias"]) == 1
    assert validar(fuente_id="NUEVO-001").json()["permitido"] is True


def test_validar_alta_exige_permiso_de_gestion(cliente) -> None:
    test_client, _qdrant = cliente
    encabezados = _encabezados(test_client, "analista@local")

    respuesta = test_client.post(
        "/curaduria/fuentes/validar-alta",
        headers=encabezados,
        json={"fuente_id": "X", "version": "1"},
    )

    assert respuesta.status_code == 403


def test_importar_la_plantilla_dos_veces_rechaza_los_ids_repetidos_con_hoja_fila_y_columna(
    cliente,
) -> None:
    test_client, _qdrant = cliente
    encabezados = _encabezados(test_client, "curador@local")
    contenido = RUTA_PLANTILLA_REAL.read_bytes()

    def subir(ruta):
        return test_client.post(
            ruta,
            headers=encabezados,
            files={"archivo": ("plantilla.xlsx", contenido, "application/octet-stream")},
        )

    primera = subir("/curaduria/plantilla/importar").json()
    assert primera["es_valido"] is True

    for ruta in ("/curaduria/plantilla/validar", "/curaduria/plantilla/importar"):
        segunda = subir(ruta).json()
        assert segunda["es_valido"] is False
        error = segunda["errores"][0]
        assert error["hoja"] == "Inventario de fuentes" and error["columna"] == "fuente_id"
        assert error["fila"] >= 2 and "Ya existe" in error["mensaje"]
