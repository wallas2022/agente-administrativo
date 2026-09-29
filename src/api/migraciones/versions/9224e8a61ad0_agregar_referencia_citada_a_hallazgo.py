"""agregar referencia_citada a hallazgo

Revision ID: 9224e8a61ad0
Revises: 60f6f728be74
Create Date: 2026-09-29 12:04:06.952802

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9224e8a61ad0'
down_revision: Union[str, None] = '60f6f728be74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Bloque K4: cita complementaria que nunca funda el hallazgo por sí
    # sola (ver comun.modelos.Hallazgo.referencia_citada / rag.busqueda.
    # construir_citas).
    op.add_column('hallazgo', sa.Column('referencia_citada', sa.String(length=300), nullable=True))


def downgrade() -> None:
    op.drop_column('hallazgo', 'referencia_citada')
