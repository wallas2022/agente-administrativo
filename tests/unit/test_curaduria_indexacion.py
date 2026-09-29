import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from comun.modelos import Area, Bitacora, Fragmento, FuenteConocimiento, Usuario
from comun.modelos import Base as ModelosBase
from curaduria.extraccion import FragmentoExtraido
from curaduria.indexacion import desactivar_fragmentos_de_fuente, indexar_fragmentos, indexar_fuente

RAIZ = Path(__file__).resolve().parents[2]
RUTA_PDF_EJEMPLO = RAIZ / "kb" / "plantillas" / "ejemplos" / "POL-001_Politica_Cierre_EJEMPLO.pdf"

COLECCION = "agente_admin_kb_prueba_k3"
DIMENSION = 4


def _embedding_falso(texto: str) -> list[float]:
    return [float(len(texto) % 7), 1.0, 0.0, 0.0]


def _sesion_en_memoria() -> Session:
    engine = create_engine("sqlite:///:memory:")
    ModelosBase.metadata.create_all(engine)
    return Session(engine)


def _fuente_vigente(
    sesion: Session, *, fuente_id: str = "POL-001", version: str = "1.0"
) -> FuenteConocimiento:
    from comun.modelos import Rol

    area = sesion.query(Area).filter_by(nombre="Contabilidad").one_or_none()
    if area is None:
        area = Area(nombre="Contabilidad")
        sesion.add(area)
        sesion.flush()
    rol = Rol(nombre="curador")
    sesion.add(rol)
    sesion.flush()
    usuario = Usuario(
        nombre="Carla Curadora",
        email=f"carla-{uuid.uuid4()}@ejemplo.gt",
        area_id=area.id,
        rol_id=rol.id,
        origen_autenticacion="local",
        activo=True,
    )
    sesion.add(usuario)
    sesion.flush()

    fuente = FuenteConocimiento(
        fuente_id=fuente_id,
        titulo="Política de cierre contable",
        tipo="regla_interna",
        prioridad=1,
        version=version,
        vigente_desde=date(2026, 1, 1),
        estado="vigente",
        area_id=area.id,
        dueno="Jefatura de Contabilidad",
        archivo="POL-001.docx",
        cargado_por=usuario.id,
        fecha_carga=datetime.now(UTC),
    )
    sesion.add(fuente)
    sesion.flush()
    return fuente


def test_indexar_fragmentos_persiste_en_postgres_y_en_qdrant() -> None:
    sesion = _sesion_en_memoria()
    fuente = _fuente_vigente(sesion)
    cliente = QdrantClient(":memory:")
    fragmentos = [
        FragmentoExtraido("Contenido de la sección 1.", "§1", None),
        FragmentoExtraido("Contenido de la sección 2.", "§2", None),
    ]

    resultado = indexar_fragmentos(
        sesion,
        cliente,
        fuente=fuente,
        area_nombre="Contabilidad",
        fragmentos=fragmentos,
        funcion_embedding=_embedding_falso,
        dimension=DIMENSION,
        coleccion=COLECCION,
    )

    assert resultado.fragmentos_indexados == 2
    assert resultado.duracion_segundos >= 0

    filas = sesion.query(Fragmento).filter_by(fuente_id=fuente.id).all()
    assert len(filas) == 2
    assert {f.pagina_o_seccion for f in filas} == {"§1", "§2"}
    assert all(f.referencia_vector for f in filas)

    conteo = cliente.count(collection_name=COLECCION).count
    assert conteo == 2

    punto = cliente.retrieve(
        collection_name=COLECCION, ids=[filas[0].referencia_vector], with_payload=True
    )[0]
    assert punto.payload["fuente_id"] == "POL-001"
    assert punto.payload["version"] == "1.0"
    assert punto.payload["tipo"] == "regla_interna"
    assert punto.payload["prioridad"] == 1
    assert punto.payload["area"] == "Contabilidad"
    assert punto.payload["estado"] == "vigente"
    assert punto.payload["seccion"] in {"§1", "§2"}


def test_indexar_fragmentos_rechaza_fuente_que_no_es_vigente() -> None:
    sesion = _sesion_en_memoria()
    fuente = _fuente_vigente(sesion)
    fuente.estado = "borrador"
    cliente = QdrantClient(":memory:")

    with pytest.raises(ValueError, match="vigente"):
        indexar_fragmentos(
            sesion,
            cliente,
            fuente=fuente,
            area_nombre="Contabilidad",
            fragmentos=[FragmentoExtraido("x", None, None)],
            funcion_embedding=_embedding_falso,
            dimension=DIMENSION,
            coleccion=COLECCION,
        )


def test_indexar_fragmentos_usa_pagina_cuando_no_hay_seccion() -> None:
    sesion = _sesion_en_memoria()
    fuente = _fuente_vigente(sesion)
    cliente = QdrantClient(":memory:")

    indexar_fragmentos(
        sesion,
        cliente,
        fuente=fuente,
        area_nombre="Contabilidad",
        fragmentos=[FragmentoExtraido("Contenido sin encabezado.", None, 3)],
        funcion_embedding=_embedding_falso,
        dimension=DIMENSION,
        coleccion=COLECCION,
    )

    fila = sesion.query(Fragmento).filter_by(fuente_id=fuente.id).one()
    assert fila.pagina_o_seccion == "Página 3"


def test_desactivar_fragmentos_de_fuente_marca_el_payload_como_obsoleta() -> None:
    sesion = _sesion_en_memoria()
    fuente = _fuente_vigente(sesion)
    cliente = QdrantClient(":memory:")
    indexar_fragmentos(
        sesion,
        cliente,
        fuente=fuente,
        area_nombre="Contabilidad",
        fragmentos=[FragmentoExtraido("Contenido.", "§1", None)],
        funcion_embedding=_embedding_falso,
        dimension=DIMENSION,
        coleccion=COLECCION,
    )

    desactivados = desactivar_fragmentos_de_fuente(
        cliente, coleccion=COLECCION, fuente_id_negocio="POL-001"
    )

    assert desactivados == 1
    fila = sesion.query(Fragmento).filter_by(fuente_id=fuente.id).one()
    puntos = cliente.retrieve(
        collection_name=COLECCION, ids=[fila.referencia_vector], with_payload=True
    )
    assert puntos[0].payload["estado"] == "obsoleta"


def test_desactivar_fragmentos_de_fuente_nunca_indexada_devuelve_cero() -> None:
    cliente = QdrantClient(":memory:")
    resultado = desactivar_fragmentos_de_fuente(
        cliente, coleccion="coleccion-inexistente", fuente_id_negocio="X"
    )
    assert resultado == 0


def test_aprobar_una_version_nueva_desactiva_solo_los_fragmentos_de_la_anterior() -> None:
    """Simula el flujo completo: v1 indexada y vigente, se aprueba v2 (misma
    fuente_id) -- solo los fragmentos de v1 quedan "obsoleta", los de v2
    quedan "vigente", y ambos siguen en la colección (no se borran)."""
    sesion = _sesion_en_memoria()
    cliente = QdrantClient(":memory:")

    v1 = _fuente_vigente(sesion, fuente_id="POL-001", version="1.0")
    indexar_fragmentos(
        sesion, cliente, fuente=v1, area_nombre="Contabilidad",
        fragmentos=[FragmentoExtraido("Contenido v1.", "§1", None)],
        funcion_embedding=_embedding_falso, dimension=DIMENSION, coleccion=COLECCION,
    )

    # aprobar_fuente (Bloque K1) ya habría pasado v1 a "obsoleta" en Postgres;
    # acá se simula el efecto equivalente en Qdrant.
    desactivar_fragmentos_de_fuente(cliente, coleccion=COLECCION, fuente_id_negocio="POL-001")
    v1.estado = "obsoleta"

    v2 = _fuente_vigente(sesion, fuente_id="POL-001", version="2.0")
    indexar_fragmentos(
        sesion, cliente, fuente=v2, area_nombre="Contabilidad",
        fragmentos=[FragmentoExtraido("Contenido v2.", "§1", None)],
        funcion_embedding=_embedding_falso, dimension=DIMENSION, coleccion=COLECCION,
    )

    assert cliente.count(collection_name=COLECCION).count == 2  # nada se borró

    fila_v1 = sesion.query(Fragmento).filter_by(fuente_id=v1.id).one()
    fila_v2 = sesion.query(Fragmento).filter_by(fuente_id=v2.id).one()
    punto_v1 = cliente.retrieve(collection_name=COLECCION, ids=[fila_v1.referencia_vector])[0]
    punto_v2 = cliente.retrieve(collection_name=COLECCION, ids=[fila_v2.referencia_vector])[0]
    assert punto_v1.payload["estado"] == "obsoleta"
    assert punto_v1.payload["version"] == "1.0"
    assert punto_v2.payload["estado"] == "vigente"
    assert punto_v2.payload["version"] == "2.0"


def test_indexar_fuente_extrae_indexa_y_registra_en_bitacora_con_el_pdf_real() -> None:
    sesion = _sesion_en_memoria()
    fuente = _fuente_vigente(sesion)
    cliente = QdrantClient(":memory:")
    usuario_id = fuente.cargado_por

    resultado = indexar_fuente(
        sesion,
        cliente,
        fuente=fuente,
        contenido_archivo=RUTA_PDF_EJEMPLO.read_bytes(),
        tipo_archivo="pdf",
        area_nombre="Contabilidad",
        funcion_embedding=_embedding_falso,
        dimension=DIMENSION,
        usuario_id=usuario_id,
        coleccion=COLECCION,
    )

    assert resultado.fragmentos_indexados == 7  # título + 6 secciones (§1..§6)
    assert sesion.query(Fragmento).filter_by(fuente_id=fuente.id).count() == 7

    bitacora = (
        sesion.query(Bitacora)
        .filter_by(entidad_id=fuente.id, accion="fuente_indexada")
        .one()
    )
    assert "7 fragmento" in bitacora.detalle
    assert "POL-001" in bitacora.detalle
    assert bitacora.usuario_id == usuario_id
