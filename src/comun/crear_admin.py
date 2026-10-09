"""Comando de rescate (P-12, Bloque 1, R-P1/R-P3): crea o actualiza el
Administrador en stage, pidiendo la contraseña por consola -- nunca como
argumento (quedaría en el historial de la shell) ni fija en el código.

Uso:
    python -m comun.crear_admin --email admin@ejemplo.gt --nombre "Admin" --area Contabilidad

Sirve también de rescate si el único Administrador quedó bloqueado o
desactivado: reactiva, desbloquea y permite poner una contraseña nueva.
"""

from __future__ import annotations

import argparse
import getpass

from sqlalchemy.orm import Session

from comun.db import obtener_fabrica_sesion
from comun.estados import RolUsuario
from comun.modelos import Area, Rol, Usuario
from comun.permisos import sembrar_permisos_por_defecto
from comun.seguridad import hash_password

LONGITUD_MINIMA_PASSWORD = 10


def _password_valida(password: str) -> bool:
    return (
        len(password) >= LONGITUD_MINIMA_PASSWORD
        and any(c.isalpha() for c in password)
        and any(c.isdigit() for c in password)
    )


def crear_o_actualizar_administrador(
    sesion: Session, *, email: str, nombre: str, area: str, password: str
) -> Usuario:
    """Idempotente: si el usuario ya existe, lo actualiza (nombre, área,
    rol, contraseña) y lo reactiva/desbloquea en vez de crear uno nuevo."""
    area_fila = sesion.query(Area).filter_by(nombre=area).one_or_none()
    if area_fila is None:
        area_fila = Area(nombre=area)
        sesion.add(area_fila)
        sesion.flush()

    rol = sesion.query(Rol).filter_by(nombre=RolUsuario.ADMINISTRADOR.value).one_or_none()
    if rol is None:
        rol = Rol(nombre=RolUsuario.ADMINISTRADOR.value)
        sesion.add(rol)
        sesion.flush()

    usuario = sesion.query(Usuario).filter_by(email=email).one_or_none()
    if usuario is None:
        usuario = Usuario(nombre=nombre, email=email, area_id=area_fila.id, rol_id=rol.id)
        sesion.add(usuario)
    else:
        usuario.nombre = nombre
        usuario.area_id = area_fila.id
        usuario.rol_id = rol.id

    usuario.password_hash = hash_password(password)
    usuario.activo = True
    usuario.debe_cambiar_password = False
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    sesion.flush()

    sembrar_permisos_por_defecto(sesion)
    sesion.commit()
    return usuario


def main() -> None:  # pragma: no cover - interactivo (getpass), probado vía la función de arriba
    parser = argparse.ArgumentParser(
        description="Crea o actualiza el Administrador (primer ingreso en stage, o rescate)."
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--nombre", required=True)
    parser.add_argument("--area", required=True)
    args = parser.parse_args()

    password = getpass.getpass("Contraseña: ")
    confirmacion = getpass.getpass("Confirmar contraseña: ")
    if password != confirmacion:
        raise SystemExit("Las contraseñas no coinciden.")
    if not _password_valida(password):
        raise SystemExit(
            f"La contraseña debe tener al menos {LONGITUD_MINIMA_PASSWORD} "
            "caracteres, con letras y números."
        )

    sesion = obtener_fabrica_sesion()()
    try:
        usuario = crear_o_actualizar_administrador(
            sesion, email=args.email, nombre=args.nombre, area=args.area, password=password
        )
        print(f"Administrador listo: {usuario.email} (área: {args.area})")
    finally:
        sesion.close()


if __name__ == "__main__":
    main()
