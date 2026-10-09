"""Matriz de permisos por defecto (P-12, RF-02) -- ver
docs/03-diseno/seguridad/roles-permisos.md v0.3, sección "Matriz
recurso:acción". Sin lógica de autorización acá (eso es
`api.main.requiere_permiso`); solo la matriz y su siembra idempotente.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from comun.estados import RolUsuario
from comun.modelos import Permiso, Rol

MATRIZ_PERMISOS_DEFECTO: dict[RolUsuario, frozenset[tuple[str, str]]] = {
    RolUsuario.ANALISTA: frozenset(
        {
            ("analisis", "crear"),
            ("historial", "propio"),
            ("historial", "area"),
        }
    ),
    RolUsuario.REVISOR: frozenset(
        {
            ("historial", "propio"),
            ("historial", "area"),
            ("hallazgos", "decidir"),
        }
    ),
    RolUsuario.CURADOR: frozenset(
        {
            ("historial", "propio"),
            ("historial", "area"),
            ("conocimiento", "ver"),
            ("conocimiento", "gestionar"),
            ("conocimiento", "aprobar"),
        }
    ),
    RolUsuario.ADMINISTRADOR: frozenset(
        {
            ("analisis", "crear"),
            ("historial", "propio"),
            ("historial", "area"),
            ("historial", "todas"),
            ("hallazgos", "decidir"),
            ("conocimiento", "ver"),
            ("bitacora", "ver"),
            ("reportes", "autoaprobados"),
            ("usuarios", "administrar"),
            ("roles", "administrar"),
            ("areas", "administrar"),
        }
    ),
    RolUsuario.AUDITOR: frozenset(
        {
            ("historial", "propio"),
            ("historial", "area"),
            ("historial", "todas"),
            ("conocimiento", "ver"),
            ("bitacora", "ver"),
            ("reportes", "autoaprobados"),
        }
    ),
}

# Universo de pares (recurso, accion) de la matriz v0.3 -- HU-23 solo deja
# marcar/desmarcar casillas de esta matriz, no inventar recursos nuevos.
TODOS_LOS_RECURSOS_ACCIONES: frozenset[tuple[str, str]] = frozenset(
    par for permisos in MATRIZ_PERMISOS_DEFECTO.values() for par in permisos
)

# Protegidos (HU-23): ni editables ni borrables desde Configuración, bajo
# ningún rol -- ver roles-permisos.md v0.3.
PERMISOS_PROTEGIDOS: frozenset[tuple[RolUsuario, str, str]] = frozenset(
    {
        (RolUsuario.ADMINISTRADOR, "bitacora", "ver"),
        (RolUsuario.AUDITOR, "bitacora", "ver"),
        (RolUsuario.ADMINISTRADOR, "usuarios", "administrar"),
        (RolUsuario.ADMINISTRADOR, "roles", "administrar"),
        (RolUsuario.ADMINISTRADOR, "areas", "administrar"),
    }
)


def es_permiso_protegido(rol: RolUsuario, recurso: str, accion: str) -> bool:
    return (rol, recurso, accion) in PERMISOS_PROTEGIDOS


def sembrar_permisos_por_defecto(sesion: Session) -> None:
    """Idempotente: no duplica filas si ya existen. Requiere que los 5
    `Rol` ya existan (ver `comun.semillas`) -- un rol que todavía no está
    sembrado simplemente se salta, no es un error."""
    for rol_usuario, permisos in MATRIZ_PERMISOS_DEFECTO.items():
        rol = sesion.query(Rol).filter_by(nombre=rol_usuario.value).one_or_none()
        if rol is None:
            continue
        existentes = {
            (p.recurso, p.accion) for p in sesion.query(Permiso).filter_by(rol_id=rol.id).all()
        }
        for recurso, accion in permisos:
            if (recurso, accion) in existentes:
                continue
            sesion.add(Permiso(rol_id=rol.id, recurso=recurso, accion=accion))
    sesion.commit()


def restaurar_matriz_por_defecto(sesion: Session) -> None:
    """HU-23 "Restaurar matriz por defecto": descarta cualquier permiso
    agregado o quitado a mano y vuelve a sembrar exactamente la matriz v0.3."""
    sesion.query(Permiso).delete()
    sesion.flush()
    sembrar_permisos_por_defecto(sesion)
