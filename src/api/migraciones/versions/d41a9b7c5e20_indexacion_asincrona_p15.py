"""indexacion_asincrona_p15

Revision ID: d41a9b7c5e20
Revises: 7fcc343bac6f
Create Date: 2026-10-14 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd41a9b7c5e20'
down_revision: Union[str, None] = '7fcc343bac6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('fuente_conocimiento', sa.Column('fragmentos_total', sa.Integer(), nullable=True))
    op.add_column('fuente_conocimiento', sa.Column('fragmentos_procesados', sa.Integer(), nullable=True))
    op.add_column('fuente_conocimiento', sa.Column('motivo_error', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('fuente_conocimiento', 'motivo_error')
    op.drop_column('fuente_conocimiento', 'fragmentos_procesados')
    op.drop_column('fuente_conocimiento', 'fragmentos_total')
