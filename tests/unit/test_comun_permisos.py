"""Pruebas de la matriz de permisos por defecto y su siembra idempotente
(P-12, Bloque 1)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from comun.estados import RolUsuario
from comun.modelos import Base, Permiso, Rol
from comun.permisos import (
    MATRIZ_PERMISOS_DEFECTO,
    es_permiso_protegido,
    restaurar_matriz_por_defecto,
    sembrar_permisos_por_defecto,
)


def _sesion_con_roles() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sesion = Session(engine)
    for rol_usuario in RolUsuario:
        sesion.add(Rol(nombre=rol_usuario.value))
    sesion.commit()
    return sesion


def test_sembrar_permisos_por_defecto_crea_una_fila_por_permiso_de_la_matriz() -> None:
    sesion = _sesion_con_roles()
    sembrar_permisos_por_defecto(sesion)

    total_esperado = sum(len(p) for p in MATRIZ_PERMISOS_DEFECTO.values())
    assert sesion.query(Permiso).count() == total_esperado


def test_sembrar_permisos_por_defecto_es_idempotente() -> None:
    sesion = _sesion_con_roles()
    sembrar_permisos_por_defecto(sesion)
    sembrar_permisos_por_defecto(sesion)

    total_esperado = sum(len(p) for p in MATRIZ_PERMISOS_DEFECTO.values())
    assert sesion.query(Permiso).count() == total_esperado


def test_sembrar_permisos_asigna_analisis_crear_solo_a_analista_y_administrador() -> None:
    sesion = _sesion_con_roles()
    sembrar_permisos_por_defecto(sesion)

    filas = sesion.query(Permiso).filter_by(recurso="analisis", accion="crear").all()
    roles_con_el_permiso = {sesion.get(Rol, f.rol_id).nombre for f in filas}
    assert roles_con_el_permiso == {RolUsuario.ANALISTA.value, RolUsuario.ADMINISTRADOR.value}


def test_sembrar_permisos_no_duplica_si_el_administrador_ya_agrego_uno_manualmente() -> None:
    sesion = _sesion_con_roles()
    rol_admin = sesion.query(Rol).filter_by(nombre=RolUsuario.ADMINISTRADOR.value).one()
    sesion.add(Permiso(rol_id=rol_admin.id, recurso="analisis", accion="crear"))
    sesion.commit()

    sembrar_permisos_por_defecto(sesion)

    filas = (
        sesion.query(Permiso)
        .filter_by(rol_id=rol_admin.id, recurso="analisis", accion="crear")
        .all()
    )
    assert len(filas) == 1


def test_restaurar_matriz_por_defecto_quita_permisos_agregados_a_mano() -> None:
    sesion = _sesion_con_roles()
    sembrar_permisos_por_defecto(sesion)
    rol_analista = sesion.query(Rol).filter_by(nombre=RolUsuario.ANALISTA.value).one()
    sesion.add(Permiso(rol_id=rol_analista.id, recurso="usuarios", accion="administrar"))
    sesion.commit()

    restaurar_matriz_por_defecto(sesion)

    filas = (
        sesion.query(Permiso)
        .filter_by(rol_id=rol_analista.id, recurso="usuarios", accion="administrar")
        .all()
    )
    assert filas == []
    total_esperado = sum(len(p) for p in MATRIZ_PERMISOS_DEFECTO.values())
    assert sesion.query(Permiso).count() == total_esperado


def test_es_permiso_protegido() -> None:
    assert es_permiso_protegido(RolUsuario.ADMINISTRADOR, "usuarios", "administrar") is True
    assert es_permiso_protegido(RolUsuario.ADMINISTRADOR, "bitacora", "ver") is True
    assert es_permiso_protegido(RolUsuario.AUDITOR, "bitacora", "ver") is True
    assert es_permiso_protegido(RolUsuario.ANALISTA, "analisis", "crear") is False
