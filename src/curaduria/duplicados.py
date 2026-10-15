"""Detección de fuentes duplicadas: mismo (fuente_id, version) en más de una fila.

Solo lee: nunca borra ni modifica nada (la decisión de cuál renombrar o retirar es del
curador). Se usa antes de crear la restricción UNIQUE (fuente_id, version) en la migración
y desde la línea de comandos:

    python -m curaduria.duplicados

Usa SQL directo sobre una conexión para funcionar también con una base anterior a la
restricción, sin depender del modelo ORM.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.engine import Connection

_CONSULTA = text(
    """
    SELECT f.id, f.fuente_id, f.version, f.titulo, f.tipo, f.estado, a.nombre AS area,
           f.fecha_carga,
           (SELECT count(*) FROM fragmento g WHERE g.fuente_id = f.id) AS fragmentos
    FROM fuente_conocimiento f
    LEFT JOIN area a ON a.id = f.area_id
    WHERE (f.fuente_id, f.version) IN (
        SELECT fuente_id, version FROM fuente_conocimiento
        GROUP BY fuente_id, version HAVING count(*) > 1
    )
    ORDER BY f.fuente_id, f.version, f.fecha_carga
    """
)


@dataclass(frozen=True)
class FilaDuplicada:
    id: str
    titulo: str
    tipo: str
    estado: str
    area: str | None
    fecha_carga: str
    fragmentos: int


@dataclass
class GrupoDuplicado:
    fuente_id: str
    version: str
    filas: list[FilaDuplicada] = field(default_factory=list)


def listar_duplicados(conexion: Connection) -> list[GrupoDuplicado]:
    grupos: dict[tuple[str, str], GrupoDuplicado] = {}
    for r in conexion.execute(_CONSULTA):
        clave = (r.fuente_id, r.version)
        grupo = grupos.setdefault(clave, GrupoDuplicado(r.fuente_id, r.version))
        grupo.filas.append(
            FilaDuplicada(
                id=str(r.id),
                titulo=r.titulo,
                tipo=r.tipo,
                estado=r.estado,
                area=r.area,
                fecha_carga=str(r.fecha_carga),
                fragmentos=int(r.fragmentos),
            )
        )
    return list(grupos.values())


def formatear_duplicados(grupos: list[GrupoDuplicado]) -> str:
    lineas = [
        f"Hay {len(grupos)} grupo(s) de fuentes con el mismo (fuente_id, versión). "
        "No se borró nada.",
        "Renombre el fuente_id (o la versión) de todas menos una, por ejemplo con:",
        "  UPDATE fuente_conocimiento SET fuente_id = '<ID-nuevo>' WHERE id = '<id de la fila>';",
        "Si la fuente ya está vigente, actualice también el payload fuente_id en Qdrant.",
        "",
    ]
    for g in grupos:
        lineas.append(f"* {g.fuente_id} versión {g.version}")
        for f in g.filas:
            lineas.append(
                f"    id={f.id} · «{f.titulo}» · {f.tipo} · estado={f.estado} · "
                f"área={f.area} · cargada={f.fecha_carga} · fragmentos={f.fragmentos}"
            )
    return "\n".join(lineas)


def main() -> int:  # pragma: no cover - utilidad de línea de comandos
    from comun.db import obtener_fabrica_sesion

    sesion = obtener_fabrica_sesion()()
    try:
        grupos = listar_duplicados(sesion.connection())
    finally:
        sesion.close()
    if not grupos:
        print("No hay fuentes duplicadas por (fuente_id, versión).")
        return 0
    print(formatear_duplicados(grupos))
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
