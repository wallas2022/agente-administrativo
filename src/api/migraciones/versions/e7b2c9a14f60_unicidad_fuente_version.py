"""unicidad_fuente_version

Revision ID: e7b2c9a14f60
Revises: d41a9b7c5e20
Create Date: 2026-10-14 18:30:00.000000

Restricción UNIQUE (fuente_id, version) en fuente_conocimiento. Antes de crearla se buscan
duplicados existentes: si los hay, la migración se detiene y los lista SIN borrar nada (el
curador decide cuál renombrar).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "e7b2c9a14f60"
down_revision: Union[str, None] = "d41a9b7c5e20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOMBRE_RESTRICCION = "ux_fuente_conocimiento_id_version"


def verificar_sin_duplicados(conexion) -> None:
    from curaduria.duplicados import formatear_duplicados, listar_duplicados

    grupos = listar_duplicados(conexion)
    if grupos:
        raise RuntimeError(
            "No se puede crear la restricción UNIQUE (fuente_id, version).\n"
            + formatear_duplicados(grupos)
            + "\nCuando no queden duplicados, vuelva a ejecutar la migración."
        )


def upgrade() -> None:
    verificar_sin_duplicados(op.get_bind())
    op.create_unique_constraint(NOMBRE_RESTRICCION, "fuente_conocimiento", ["fuente_id", "version"])


def downgrade() -> None:
    op.drop_constraint(NOMBRE_RESTRICCION, "fuente_conocimiento", type_="unique")
