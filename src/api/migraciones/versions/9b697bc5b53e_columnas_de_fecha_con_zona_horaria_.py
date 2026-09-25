"""columnas de fecha con zona horaria (timestamptz)

Revision ID: 9b697bc5b53e
Revises: 7236da454602
Create Date: 2026-09-25 13:55:26.568378

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9b697bc5b53e'
down_revision: Union[str, None] = '7236da454602'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Se agrega "USING ... AT TIME ZONE 'UTC'" a mano (Alembic no lo infiere):
    # el código siempre escribió datetime.now(UTC), pero como la columna era
    # TIMESTAMP WITHOUT TIME ZONE, Postgres descartaba esa información. Sin
    # esta cláusula, el ALTER COLUMN por defecto reinterpretaría los valores
    # ya guardados según el timezone de la sesión (ambiguo), no como UTC.
    op.alter_column(
        'analisis', 'fecha_inicio',
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="fecha_inicio AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        'analisis', 'fecha_fin',
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
        postgresql_using="fecha_fin AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        'bitacora', 'fecha_hora',
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="fecha_hora AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        'decision', 'fecha',
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="fecha AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        'documento', 'fecha_carga',
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="fecha_carga AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        'version_documento', 'fecha_creacion',
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="fecha_creacion AT TIME ZONE 'UTC'",
    )


def downgrade() -> None:
    op.alter_column(
        'version_documento', 'fecha_creacion',
        existing_type=sa.DateTime(timezone=True),
        type_=postgresql.TIMESTAMP(),
        existing_nullable=False,
        postgresql_using="fecha_creacion AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        'documento', 'fecha_carga',
        existing_type=sa.DateTime(timezone=True),
        type_=postgresql.TIMESTAMP(),
        existing_nullable=False,
        postgresql_using="fecha_carga AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        'decision', 'fecha',
        existing_type=sa.DateTime(timezone=True),
        type_=postgresql.TIMESTAMP(),
        existing_nullable=False,
        postgresql_using="fecha AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        'bitacora', 'fecha_hora',
        existing_type=sa.DateTime(timezone=True),
        type_=postgresql.TIMESTAMP(),
        existing_nullable=False,
        postgresql_using="fecha_hora AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        'analisis', 'fecha_fin',
        existing_type=sa.DateTime(timezone=True),
        type_=postgresql.TIMESTAMP(),
        existing_nullable=True,
        postgresql_using="fecha_fin AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        'analisis', 'fecha_inicio',
        existing_type=sa.DateTime(timezone=True),
        type_=postgresql.TIMESTAMP(),
        existing_nullable=False,
        postgresql_using="fecha_inicio AT TIME ZONE 'UTC'",
    )
