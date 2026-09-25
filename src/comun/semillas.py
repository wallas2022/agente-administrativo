"""Datos semilla para el ambiente de desarrollo/pruebas: un Área, un Rol por
cada rol del SRS y un Usuario por cada usuario local de prueba (comun.seguridad).
Idempotente: no duplica filas si ya existen. Sin lógica de negocio real.
"""

from sqlalchemy.orm import Session

from comun.estados import RolUsuario
from comun.modelos import Area, Rol, Usuario

AREA_DE_PRUEBA = "Contabilidad"


def sembrar_datos_de_prueba(sesion: Session) -> dict[str, Usuario]:
    area = sesion.query(Area).filter_by(nombre=AREA_DE_PRUEBA).one_or_none()
    if area is None:
        area = Area(nombre=AREA_DE_PRUEBA)
        sesion.add(area)
        sesion.flush()

    usuarios: dict[str, Usuario] = {}
    for rol_usuario in RolUsuario:
        rol = sesion.query(Rol).filter_by(nombre=rol_usuario.value).one_or_none()
        if rol is None:
            rol = Rol(nombre=rol_usuario.value)
            sesion.add(rol)
            sesion.flush()

        email = f"{rol_usuario.value}@local"
        usuario = sesion.query(Usuario).filter_by(email=email).one_or_none()
        if usuario is None:
            usuario = Usuario(
                nombre=rol_usuario.value.capitalize(),
                email=email,
                area_id=area.id,
                rol_id=rol.id,
                origen_autenticacion="local",
                activo=True,
            )
            sesion.add(usuario)
            sesion.flush()
        usuarios[email] = usuario

    sesion.commit()
    return usuarios
