"""sha256 de fuente_conocimiento opcional hasta cargar el binario

Revision ID: 60f6f728be74
Revises: b94798a2e582
Create Date: 2026-09-29 11:33:15.246519

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '60f6f728be74'
down_revision: Union[str, None] = 'b94798a2e582'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Bloque K2: el importador de la plantilla registra una FuenteConocimiento
    # "borrador" por cada fila de "Inventario de fuentes" aunque el binario
    # real (.docx/.pdf) todavía no se haya adjuntado -- el curador puede
    # llenar la plantilla antes de subir los documentos uno por uno. El
    # sha256 se calcula cuando el binario efectivamente llega (import con
    # adjuntos, o "subir nueva versión" del Bloque K5); hasta entonces queda
    # NULL, no un valor inventado.
    op.alter_column('fuente_conocimiento', 'sha256', nullable=True)


def downgrade() -> None:
    op.alter_column('fuente_conocimiento', 'sha256', nullable=False)
