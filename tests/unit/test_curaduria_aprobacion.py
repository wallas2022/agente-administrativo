"""P-15 Bloque 3: aprobación asíncrona -- iniciar_indexacion + procesar_indexacion
(estados indexando -> vigente | error_indexacion, progreso y bitácora)."""

from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from comun.almacenamiento import ObjetoNoEncontradoError
from comun.modelos import Area, Bitacora, Fragmento, FuenteConocimiento, Rol, Usuario
from comun.modelos import Base as ModelosBase
from curaduria.aprobacion import iniciar_indexacion, procesar_indexacion

RAIZ = Path(__file__).resolve().parents[2]
PDF = RAIZ / "kb" / "plantillas" / "ejemplos" / "POL-001_Politica_Cierre_EJEMPLO.pdf"
COLECCION = "kb_prueba_p15_b3"
DIMENSION = 4
FRAGMENTOS_DEL_PDF = 7  # título + §1..§6


def _embedding_falso(texto: str) -> list[float]:
    return [float(len(texto) % 7), 1.0, 0.0, 0.0]


class _Entorno:
    def __init__(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        ModelosBase.metadata.create_all(engine)
        self.sesion = Session(engine)
        self.qdrant = QdrantClient(":memory:")
        area = Area(nombre="Contabilidad")
        rol = Rol(nombre="curador")
        self.sesion.add_all([area, rol])
        self.sesion.flush()
        self.usuario = Usuario(
            nombre="Carla",
            email="carla@ejemplo.gt",
            area_id=area.id,
            rol_id=rol.id,
            origen_autenticacion="local",
            activo=True,
        )
        self.sesion.add(self.usuario)
        self.sesion.flush()
        self.area = area

    def fuente(self, *, version: str, estado: str = "borrador") -> FuenteConocimiento:
        fila = FuenteConocimiento(
            fuente_id="POL-001",
            titulo="Política de cierre",
            tipo="regla_interna",
            prioridad=1,
            version=version,
            vigente_desde=date(2026, 1, 1),
            estado=estado,
            area_id=self.area.id,
            dueno="Jefatura",
            archivo="POL-001.pdf",
            cargado_por=self.usuario.id,
            fecha_carga=datetime.now(UTC),
        )
        self.sesion.add(fila)
        self.sesion.commit()
        return fila

    def procesar(self, fuente, *, embedding=_embedding_falso, contenido=None):
        return procesar_indexacion(
            self.sesion,
            self.qdrant,
            fuente_id=fuente.id,
            usuario_id=self.usuario.id,
            obtener_contenido=contenido or PDF.read_bytes,
            funcion_embedding=embedding,
            dimension=DIMENSION,
            coleccion=COLECCION,
        )

    def acciones(self, fuente) -> list[str]:
        filas = self.sesion.query(Bitacora).filter_by(entidad_id=fuente.id).all()
        return sorted(f.accion for f in filas)

    def estados_qdrant(self, fuente) -> set[str]:
        filas = self.sesion.query(Fragmento).filter_by(fuente_id=fuente.id).all()
        if not filas:
            return set()
        puntos = self.qdrant.retrieve(
            COLECCION, ids=[f.referencia_vector for f in filas], with_payload=True
        )
        return {p.payload["estado"] for p in puntos}


@pytest.fixture()
def entorno() -> _Entorno:
    return _Entorno()


def test_iniciar_indexacion_pasa_de_borrador_a_indexando_y_deja_bitacora(entorno) -> None:
    fuente = entorno.fuente(version="1")
    iniciar_indexacion(entorno.sesion, fuente, usuario_id=entorno.usuario.id)

    assert fuente.estado == "indexando"
    assert fuente.motivo_error is None
    assert "fuente_indexacion_iniciada" in entorno.acciones(fuente)


def test_iniciar_indexacion_rechaza_estados_que_no_corresponden(entorno) -> None:
    for estado in ("vigente", "obsoleta", "indexando"):
        fuente = entorno.fuente(version=f"x-{estado}", estado=estado)
        with pytest.raises(ValueError, match=estado):
            iniciar_indexacion(entorno.sesion, fuente, usuario_id=entorno.usuario.id)


def test_procesar_deja_la_fuente_vigente_con_progreso_y_bitacora(entorno) -> None:
    fuente = entorno.fuente(version="1")
    iniciar_indexacion(entorno.sesion, fuente, usuario_id=entorno.usuario.id)

    resultado = entorno.procesar(fuente)

    assert resultado.estado == "vigente"
    assert resultado.fragmentos_indexados == FRAGMENTOS_DEL_PDF
    assert resultado.version_anterior_obsoleta is False
    entorno.sesion.refresh(fuente)
    assert fuente.estado == "vigente"
    assert fuente.aprobado_por == entorno.usuario.id
    assert fuente.fragmentos_total == fuente.fragmentos_procesados == FRAGMENTOS_DEL_PDF
    assert entorno.estados_qdrant(fuente) == {"vigente"}
    acciones = entorno.acciones(fuente)
    assert {"fuente_indexacion_iniciada", "fuente_aprobada", "fuente_indexada"} <= set(acciones)


def test_la_version_anterior_sigue_vigente_mientras_indexa_y_se_obsoletea_al_final(
    entorno,
) -> None:
    anterior = entorno.fuente(version="1")
    iniciar_indexacion(entorno.sesion, anterior, usuario_id=entorno.usuario.id)
    entorno.procesar(anterior)

    nueva = entorno.fuente(version="2")
    iniciar_indexacion(entorno.sesion, nueva, usuario_id=entorno.usuario.id)
    observado: dict[str, object] = {}

    def embedding_que_observa(texto: str) -> list[float]:
        if "estado_anterior" not in observado:
            observado["estado_anterior"] = entorno.sesion.get(
                FuenteConocimiento, anterior.id
            ).estado
            observado["qdrant_anterior"] = entorno.estados_qdrant(anterior)
        return _embedding_falso(texto)

    resultado = entorno.procesar(nueva, embedding=embedding_que_observa)

    assert observado == {"estado_anterior": "vigente", "qdrant_anterior": {"vigente"}}
    assert resultado.version_anterior_obsoleta is True
    entorno.sesion.refresh(anterior)
    entorno.sesion.refresh(nueva)
    assert (anterior.estado, nueva.estado) == ("obsoleta", "vigente")
    assert entorno.estados_qdrant(anterior) == {"obsoleta"}
    assert entorno.estados_qdrant(nueva) == {"vigente"}


def test_el_progreso_es_consultable_durante_la_indexacion(entorno) -> None:
    fuente = entorno.fuente(version="1")
    iniciar_indexacion(entorno.sesion, fuente, usuario_id=entorno.usuario.id)
    vistos: list[tuple[int | None, int | None]] = []

    def embedding_que_mira_progreso(texto: str) -> list[float]:
        vistos.append((fuente.fragmentos_procesados, fuente.fragmentos_total))
        return _embedding_falso(texto)

    entorno.procesar(fuente, embedding=embedding_que_mira_progreso)

    assert vistos[0] == (0, FRAGMENTOS_DEL_PDF)
    assert vistos[3] == (3, FRAGMENTOS_DEL_PDF)


def test_si_falla_un_embedding_queda_error_indexacion_sin_tocar_lo_vigente(entorno) -> None:
    anterior = entorno.fuente(version="1")
    iniciar_indexacion(entorno.sesion, anterior, usuario_id=entorno.usuario.id)
    entorno.procesar(anterior)
    nueva = entorno.fuente(version="2")
    iniciar_indexacion(entorno.sesion, nueva, usuario_id=entorno.usuario.id)
    llamadas = {"n": 0}

    def embedding_con_timeout(texto: str) -> list[float]:
        llamadas["n"] += 1
        if llamadas["n"] == 3:
            raise httpx.ReadTimeout("tiempo agotado")
        return _embedding_falso(texto)

    resultado = entorno.procesar(nueva, embedding=embedding_con_timeout)

    assert resultado.estado == "error_indexacion"
    assert "tardó demasiado" in resultado.motivo
    entorno.sesion.refresh(nueva)
    entorno.sesion.refresh(anterior)
    assert nueva.estado == "error_indexacion"
    assert nueva.motivo_error == resultado.motivo
    assert anterior.estado == "vigente"
    assert entorno.estados_qdrant(anterior) == {"vigente"}
    assert entorno.sesion.query(Fragmento).filter_by(fuente_id=nueva.id).count() == 0
    assert "fuente_indexacion_fallida" in entorno.acciones(nueva)


def test_objeto_ausente_deja_error_indexacion_con_mensaje_claro(entorno) -> None:
    fuente = entorno.fuente(version="1")
    iniciar_indexacion(entorno.sesion, fuente, usuario_id=entorno.usuario.id)

    def contenido_ausente() -> bytes:
        raise ObjetoNoEncontradoError("conocimiento/POL-001.pdf")

    resultado = entorno.procesar(fuente, contenido=contenido_ausente)

    assert resultado.estado == "error_indexacion"
    assert resultado.motivo == (
        "El archivo de la fuente no está en el almacenamiento; súbalo de nuevo"
    )


def test_reintentar_tras_un_error_indexa_sin_duplicar_fragmentos(entorno) -> None:
    fuente = entorno.fuente(version="1")
    iniciar_indexacion(entorno.sesion, fuente, usuario_id=entorno.usuario.id)
    llamadas = {"n": 0}

    def falla_una_vez(texto: str) -> list[float]:
        llamadas["n"] += 1
        if llamadas["n"] == 4:
            raise RuntimeError("falla transitoria")
        return _embedding_falso(texto)

    assert entorno.procesar(fuente, embedding=falla_una_vez).estado == "error_indexacion"

    iniciar_indexacion(entorno.sesion, fuente, usuario_id=entorno.usuario.id)
    assert "fuente_indexacion_reintentada" in entorno.acciones(fuente)
    assert entorno.procesar(fuente).estado == "vigente"

    assert (
        entorno.sesion.query(Fragmento).filter_by(fuente_id=fuente.id).count() == FRAGMENTOS_DEL_PDF
    )
    assert entorno.qdrant.count(COLECCION).count == FRAGMENTOS_DEL_PDF
