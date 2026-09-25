from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from comun.estados import RolUsuario
from comun.modelos import Base, Usuario
from comun.semillas import sembrar_datos_de_prueba


def _sesion() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_sembrar_datos_de_prueba_crea_un_usuario_por_rol() -> None:
    sesion = _sesion()

    usuarios = sembrar_datos_de_prueba(sesion)

    assert set(usuarios.keys()) == {f"{r.value}@local" for r in RolUsuario}
    assert sesion.query(Usuario).count() == len(RolUsuario)


def test_sembrar_datos_de_prueba_es_idempotente() -> None:
    sesion = _sesion()

    sembrar_datos_de_prueba(sesion)
    sembrar_datos_de_prueba(sesion)

    assert sesion.query(Usuario).count() == len(RolUsuario)
