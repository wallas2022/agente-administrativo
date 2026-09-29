import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from comun.modelos import Area, FuenteConocimiento, Usuario
from comun.modelos import Base as ModelosBase
from curaduria.fuentes import TIPOS_VALIDOS, aprobar_fuente, prioridad_de_tipo


def _sesion_en_memoria() -> Session:
    engine = create_engine("sqlite:///:memory:")
    ModelosBase.metadata.create_all(engine)
    return Session(engine)


def _area_y_usuario(sesion: Session) -> tuple[Area, Usuario]:
    from comun.modelos import Rol

    area = Area(nombre="Contabilidad")
    rol = Rol(nombre="curador")
    sesion.add_all([area, rol])
    sesion.flush()
    usuario = Usuario(
        nombre="Carla Curadora",
        email="carla@ejemplo.gt",
        area_id=area.id,
        rol_id=rol.id,
        origen_autenticacion="local",
        activo=True,
    )
    sesion.add(usuario)
    sesion.flush()
    return area, usuario


def _fuente_borrador(
    *, area_id: uuid.UUID, usuario_id: uuid.UUID, fuente_id: str, version: str
) -> FuenteConocimiento:
    return FuenteConocimiento(
        fuente_id=fuente_id,
        titulo="Política de cierre contable",
        tipo="normativa",
        prioridad=prioridad_de_tipo("normativa"),
        version=version,
        vigente_desde=date(2026, 1, 1),
        estado="borrador",
        area_id=area_id,
        dueno="Jefatura de Contabilidad",
        archivo="fuentes/politica.pdf",
        sha256="a" * 64,
        cargado_por=usuario_id,
        fecha_carga=datetime.now(UTC),
    )


@pytest.mark.parametrize(
    ("tipo", "esperado"), [("regla_interna", 1), ("normativa", 2), ("referencia", 3)]
)
def test_prioridad_de_tipo_mapea_los_tres_tipos_validos(tipo: str, esperado: int) -> None:
    assert prioridad_de_tipo(tipo) == esperado


def test_prioridad_de_tipo_rechaza_valores_invalidos() -> None:
    with pytest.raises(ValueError, match="tipo de fuente inválido"):
        prioridad_de_tipo("catalogo")


def test_tipos_validos_expone_exactamente_los_tres_tipos() -> None:
    assert TIPOS_VALIDOS == {"regla_interna", "normativa", "referencia"}


def test_aprobar_fuente_sin_version_anterior_no_devuelve_nada() -> None:
    sesion = _sesion_en_memoria()
    area, usuario = _area_y_usuario(sesion)
    fuente = _fuente_borrador(
        area_id=area.id, usuario_id=usuario.id, fuente_id="POL-001", version="1.0"
    )
    sesion.add(fuente)
    sesion.flush()

    ahora = datetime.now(UTC)
    resultado = aprobar_fuente(sesion, fuente, aprobado_por=usuario.id, ahora=ahora)

    assert resultado is None
    assert fuente.estado == "vigente"
    assert fuente.aprobado_por == usuario.id
    assert fuente.fecha_aprobacion == ahora


def test_aprobar_fuente_obsoletea_automaticamente_la_version_vigente_anterior() -> None:
    sesion = _sesion_en_memoria()
    area, usuario = _area_y_usuario(sesion)

    v1 = _fuente_borrador(
        area_id=area.id, usuario_id=usuario.id, fuente_id="POL-001", version="1.0"
    )
    sesion.add(v1)
    sesion.flush()
    aprobar_fuente(sesion, v1, aprobado_por=usuario.id, ahora=datetime.now(UTC))
    assert v1.estado == "vigente"

    v2 = _fuente_borrador(
        area_id=area.id, usuario_id=usuario.id, fuente_id="POL-001", version="2.0"
    )
    sesion.add(v2)
    sesion.flush()

    anterior = aprobar_fuente(sesion, v2, aprobado_por=usuario.id, ahora=datetime.now(UTC))

    assert anterior is v1
    assert v1.estado == "obsoleta"
    assert v2.estado == "vigente"
    # La versión obsoleta no se borra (RNF-06).
    assert sesion.get(FuenteConocimiento, v1.id) is not None


def test_aprobar_fuente_no_toca_versiones_vigentes_de_otro_fuente_id() -> None:
    sesion = _sesion_en_memoria()
    area, usuario = _area_y_usuario(sesion)

    otra_vigente = _fuente_borrador(
        area_id=area.id, usuario_id=usuario.id, fuente_id="POL-002", version="1.0"
    )
    sesion.add(otra_vigente)
    sesion.flush()
    aprobar_fuente(sesion, otra_vigente, aprobado_por=usuario.id, ahora=datetime.now(UTC))

    nueva = _fuente_borrador(
        area_id=area.id, usuario_id=usuario.id, fuente_id="POL-001", version="1.0"
    )
    sesion.add(nueva)
    sesion.flush()

    anterior = aprobar_fuente(sesion, nueva, aprobado_por=usuario.id, ahora=datetime.now(UTC))

    assert anterior is None
    assert otra_vigente.estado == "vigente"


def test_dos_fuentes_vigentes_con_el_mismo_fuente_id_violan_el_indice_unico() -> None:
    """El invariante también está reforzado en la base de datos (no solo en
    aprobar_fuente): insertar dos filas "vigente" con el mismo fuente_id a
    mano (sin pasar por aprobar_fuente) debe fallar."""
    sesion = _sesion_en_memoria()
    area, usuario = _area_y_usuario(sesion)

    v1 = _fuente_borrador(
        area_id=area.id, usuario_id=usuario.id, fuente_id="POL-001", version="1.0"
    )
    v1.estado = "vigente"
    v2 = _fuente_borrador(
        area_id=area.id, usuario_id=usuario.id, fuente_id="POL-001", version="2.0"
    )
    v2.estado = "vigente"
    sesion.add_all([v1, v2])

    with pytest.raises(IntegrityError):
        sesion.flush()
