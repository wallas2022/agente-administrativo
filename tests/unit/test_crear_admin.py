"""Pruebas de `comun.crear_admin` (P-12, Bloque 1, R-P1/R-P3): comando de
rescate para crear/actualizar el primer Administrador en stage, sin
contraseñas fijas en el código."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from comun.crear_admin import crear_o_actualizar_administrador
from comun.estados import RolUsuario
from comun.modelos import Area, Base, Permiso, Rol, Usuario
from comun.seguridad import verificar_password


def _sesion() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_crea_area_rol_y_usuario_si_no_existen() -> None:
    sesion = _sesion()

    usuario = crear_o_actualizar_administrador(
        sesion, email="admin@sfc.gt", nombre="Admin", area="Contabilidad", password="Clave12345"
    )

    assert sesion.query(Usuario).count() == 1
    assert sesion.query(Area).filter_by(nombre="Contabilidad").count() == 1
    rol = sesion.query(Rol).filter_by(nombre=RolUsuario.ADMINISTRADOR.value).one()
    assert usuario.rol_id == rol.id
    assert usuario.activo is True
    assert usuario.debe_cambiar_password is False
    assert verificar_password("Clave12345", usuario.password_hash)


def test_tambien_siembra_los_permisos_por_defecto() -> None:
    sesion = _sesion()
    crear_o_actualizar_administrador(
        sesion, email="admin@sfc.gt", nombre="Admin", area="Contabilidad", password="Clave12345"
    )
    assert sesion.query(Permiso).count() > 0


def test_es_idempotente_no_duplica_nada() -> None:
    sesion = _sesion()
    crear_o_actualizar_administrador(
        sesion, email="admin@sfc.gt", nombre="Admin", area="Contabilidad", password="Clave12345"
    )
    crear_o_actualizar_administrador(
        sesion, email="admin@sfc.gt", nombre="Admin", area="Contabilidad", password="OtraClave99"
    )

    assert sesion.query(Usuario).count() == 1
    assert sesion.query(Area).filter_by(nombre="Contabilidad").count() == 1
    assert sesion.query(Rol).filter_by(nombre=RolUsuario.ADMINISTRADOR.value).count() == 1


def test_rescate_reactiva_y_desbloquea_un_administrador_existente() -> None:
    """R-P1: si el único Administrador quedó bloqueado/desactivado, este
    comando es la vía de rescate -- reactiva y limpia el bloqueo."""
    sesion = _sesion()
    usuario = crear_o_actualizar_administrador(
        sesion, email="admin@sfc.gt", nombre="Admin", area="Contabilidad", password="Clave12345"
    )
    usuario.activo = False
    usuario.intentos_fallidos = 5
    from datetime import UTC, datetime, timedelta

    usuario.bloqueado_hasta = datetime.now(UTC) + timedelta(minutes=15)
    sesion.commit()

    rescatado = crear_o_actualizar_administrador(
        sesion, email="admin@sfc.gt", nombre="Admin", area="Contabilidad", password="NuevaClave1"
    )

    assert rescatado.activo is True
    assert rescatado.intentos_fallidos == 0
    assert rescatado.bloqueado_hasta is None
    assert verificar_password("NuevaClave1", rescatado.password_hash)


def test_actualiza_la_contrasena_si_el_usuario_ya_existe() -> None:
    sesion = _sesion()
    crear_o_actualizar_administrador(
        sesion, email="admin@sfc.gt", nombre="Admin", area="Contabilidad", password="Clave12345"
    )
    crear_o_actualizar_administrador(
        sesion, email="admin@sfc.gt", nombre="Admin", area="Contabilidad", password="ClaveNueva2"
    )

    usuario = sesion.query(Usuario).filter_by(email="admin@sfc.gt").one()
    assert verificar_password("ClaveNueva2", usuario.password_hash)
    assert not verificar_password("Clave12345", usuario.password_hash)
