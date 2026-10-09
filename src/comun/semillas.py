"""Datos semilla para el ambiente de desarrollo/pruebas: un Área, un Rol por
cada rol del SRS, un Usuario por cada usuario local de prueba y los permisos
por defecto (comun.permisos). Idempotente: no duplica filas si ya existen.
Sin lógica de negocio real.

Solo se invoca con APP_ENV=local (ver api/main.py, ciclo de vida de la app)
-- P-12 (R-P3): en stage, el primer Administrador se crea con
`python -m comun.crear_admin`, nunca con esta contraseña pública.
"""

from sqlalchemy.orm import Session

from comun.estados import RolUsuario
from comun.modelos import Area, Rol, Usuario
from comun.permisos import sembrar_permisos_por_defecto
from comun.seguridad import hash_password

AREA_DE_PRUEBA = "Contabilidad"
# Pública a propósito (RF-01): no protege datos reales, es solo para
# desarrollo local y las pruebas E2E (ver src/ui/e2e/ayudantes.ts).
CONTRASENA_DE_PRUEBA = "cambiar123"


def sembrar_datos_de_prueba(sesion: Session) -> dict[str, Usuario]:
    area = sesion.query(Area).filter_by(nombre=AREA_DE_PRUEBA).one_or_none()
    if area is None:
        area = Area(nombre=AREA_DE_PRUEBA)
        sesion.add(area)
        sesion.flush()

    password_hash = hash_password(CONTRASENA_DE_PRUEBA)
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
                password_hash=password_hash,
                # Conveniencia de desarrollo/E2E: estos usuarios ya están
                # "activados", a diferencia de uno real creado desde
                # Configuración (HU-22), que sí debe cambiarla (HU-25).
                debe_cambiar_password=False,
            )
            sesion.add(usuario)
            sesion.flush()
        elif usuario.password_hash is None:
            # Backfill (encontrado en vivo, P-12): una base de datos que ya
            # tenía estos usuarios ANTES de este bloque (de antes de que
            # Usuario tuviera password_hash) los deja sin contraseña para
            # siempre si no se completa acá -- sembrar_datos_de_prueba corre
            # en cada arranque de la API (APP_ENV=local), pero el `if
            # usuario is None` de arriba nunca vuelve a tocar una fila ya
            # existente.
            usuario.password_hash = password_hash
            usuario.debe_cambiar_password = False
        usuarios[email] = usuario

    sesion.flush()
    sembrar_permisos_por_defecto(sesion)
    sesion.commit()
    return usuarios
