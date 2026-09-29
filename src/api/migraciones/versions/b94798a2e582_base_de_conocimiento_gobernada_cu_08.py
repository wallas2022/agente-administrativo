"""base de conocimiento gobernada CU-08

Revision ID: b94798a2e582
Revises: a1c4e7f9b2d3
Create Date: 2026-09-29 11:21:00.010037

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b94798a2e582'
down_revision: Union[str, None] = 'a1c4e7f9b2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # fuente_conocimiento: reescritura del Bloque K1 (RF-16, CU-08). La
    # tabla no tiene filas reales en ningún ambiente todavía -- RF-16 no
    # tenía módulo de carga hasta este bloque -- de ahí que las columnas
    # nuevas NOT NULL se agreguen directo, sin server_default ni backfill.
    op.alter_column('fuente_conocimiento', 'nombre', new_column_name='titulo')
    op.alter_column('fuente_conocimiento', 'ruta_archivo', new_column_name='archivo')
    op.alter_column('fuente_conocimiento', 'curador_id', new_column_name='cargado_por')
    op.alter_column('fuente_conocimiento', 'estado', server_default='borrador')
    # alter_column no renombra el FK constraint asociado -- se hace aparte
    # para que el nombre no quede desalineado con la columna.
    op.execute(
        'ALTER TABLE fuente_conocimiento '
        'RENAME CONSTRAINT fuente_conocimiento_curador_id_fkey '
        'TO fuente_conocimiento_cargado_por_fkey'
    )

    op.add_column('fuente_conocimiento', sa.Column('fuente_id', sa.String(length=50), nullable=False))
    op.add_column('fuente_conocimiento', sa.Column('tipo', sa.String(length=20), nullable=False))
    op.add_column('fuente_conocimiento', sa.Column('prioridad', sa.Integer(), nullable=False))
    op.add_column('fuente_conocimiento', sa.Column('dueno', sa.String(length=200), nullable=False))
    op.add_column('fuente_conocimiento', sa.Column('sha256', sa.String(length=64), nullable=False))
    op.add_column('fuente_conocimiento', sa.Column('aprobado_por', sa.Uuid(), nullable=True))
    op.add_column(
        'fuente_conocimiento', sa.Column('fecha_carga', sa.DateTime(timezone=True), nullable=False)
    )
    op.add_column(
        'fuente_conocimiento', sa.Column('fecha_aprobacion', sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        'fuente_conocimiento_aprobado_por_fkey',
        'fuente_conocimiento',
        'usuario',
        ['aprobado_por'],
        ['id'],
    )
    # Invariante del Bloque K1: como mucho una fila "vigente" por fuente_id
    # -- ver comun.modelos.FuenteConocimiento y curaduria.fuentes.aprobar_fuente.
    op.create_index(
        'ux_fuente_conocimiento_una_vigente',
        'fuente_conocimiento',
        ['fuente_id'],
        unique=True,
        postgresql_where=sa.text("estado = 'vigente'"),
    )

    # glosario: version + vigente_desde (Bloque K1, hoja "Glosario" de la
    # plantilla de importación, Bloque K2).
    op.add_column('glosario', sa.Column('version', sa.String(length=50), nullable=True))
    op.add_column('glosario', sa.Column('vigente_desde', sa.Date(), nullable=True))

    # cuenta_contable: reemplaza kb/fuentes/catalogo-cuentas-contabilidad.csv
    # como fuente de verdad de RN-02 (Bloque K4).
    op.create_table(
        'cuenta_contable',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('codigo', sa.String(length=20), nullable=False),
        sa.Column('nombre', sa.String(length=300), nullable=False),
        sa.Column('tipo', sa.String(length=50), nullable=True),
        sa.Column('naturaleza', sa.String(length=20), nullable=True),
        sa.Column('acepta_movimiento', sa.Boolean(), nullable=False),
        sa.Column('notas', sa.Text(), nullable=True),
        sa.Column('area_id', sa.Uuid(), nullable=False),
        sa.Column('fuente_id', sa.Uuid(), nullable=True),
        sa.Column('version', sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(['area_id'], ['area.id']),
        sa.ForeignKeyConstraint(['fuente_id'], ['fuente_conocimiento.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('area_id', 'codigo', name='ux_cuenta_contable_area_codigo'),
    )

    # checklist_cierre: nueva -- hoja "Checklist de cierre" de la plantilla,
    # no reemplaza ningún CSV previo.
    op.create_table(
        'checklist_cierre',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('numero', sa.Integer(), nullable=False),
        sa.Column('actividad', sa.Text(), nullable=False),
        sa.Column('responsable', sa.String(length=200), nullable=True),
        sa.Column('plazo', sa.String(length=100), nullable=True),
        sa.Column('evidencia_requerida', sa.String(length=300), nullable=True),
        sa.Column('area_id', sa.Uuid(), nullable=False),
        sa.Column('fuente_id', sa.Uuid(), nullable=True),
        sa.Column('version', sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(['area_id'], ['area.id']),
        sa.ForeignKeyConstraint(['fuente_id'], ['fuente_conocimiento.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('checklist_cierre')
    op.drop_table('cuenta_contable')

    op.drop_column('glosario', 'vigente_desde')
    op.drop_column('glosario', 'version')

    op.drop_index('ux_fuente_conocimiento_una_vigente', table_name='fuente_conocimiento')
    op.drop_constraint(
        'fuente_conocimiento_aprobado_por_fkey', 'fuente_conocimiento', type_='foreignkey'
    )
    op.drop_column('fuente_conocimiento', 'fecha_aprobacion')
    op.drop_column('fuente_conocimiento', 'fecha_carga')
    op.drop_column('fuente_conocimiento', 'aprobado_por')
    op.drop_column('fuente_conocimiento', 'sha256')
    op.drop_column('fuente_conocimiento', 'dueno')
    op.drop_column('fuente_conocimiento', 'prioridad')
    op.drop_column('fuente_conocimiento', 'tipo')
    op.drop_column('fuente_conocimiento', 'fuente_id')
    op.alter_column('fuente_conocimiento', 'estado', server_default=None)
    op.execute(
        'ALTER TABLE fuente_conocimiento '
        'RENAME CONSTRAINT fuente_conocimiento_cargado_por_fkey '
        'TO fuente_conocimiento_curador_id_fkey'
    )
    op.alter_column('fuente_conocimiento', 'cargado_por', new_column_name='curador_id')
    op.alter_column('fuente_conocimiento', 'archivo', new_column_name='ruta_archivo')
    op.alter_column('fuente_conocimiento', 'titulo', new_column_name='nombre')
