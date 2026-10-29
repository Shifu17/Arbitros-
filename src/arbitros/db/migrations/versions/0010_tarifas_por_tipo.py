"""tarifas por tipo de partido y monto que paga cada equipo

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-29 10:00:00

Las tarifas existentes quedan en el tipo principal de su liga (`ligas.modalidad`).
"""
from alembic import op
import sqlalchemy as sa


revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('tarifas_nuevas',
    sa.Column('liga_id', sa.Integer(), nullable=False),
    sa.Column('modalidad', sa.String(length=20), nullable=False),
    sa.Column('posicion', sa.String(length=20), nullable=False),
    sa.Column('monto_centavos', sa.Integer(), nullable=False),
    sa.Column('cuota_equipo_centavos', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['liga_id'], ['ligas.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('liga_id', 'modalidad', 'posicion')
    )
    op.execute(
        "INSERT INTO tarifas_nuevas (liga_id, modalidad, posicion, monto_centavos) "
        "SELECT t.liga_id, COALESCE(l.modalidad, 'futbol_11'), t.posicion, t.monto_centavos "
        "FROM tarifas t JOIN ligas l ON l.id = t.liga_id"
    )
    op.drop_table('tarifas')
    op.rename_table('tarifas_nuevas', 'tarifas')

    with op.batch_alter_table('tarifas_categoria', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cuota_equipo_centavos', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('tarifas_categoria', schema=None) as batch_op:
        batch_op.drop_column('cuota_equipo_centavos')

    op.create_table('tarifas_viejas',
    sa.Column('liga_id', sa.Integer(), nullable=False),
    sa.Column('posicion', sa.String(length=20), nullable=False),
    sa.Column('monto_centavos', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['liga_id'], ['ligas.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('liga_id', 'posicion')
    )
    op.execute(
        "INSERT INTO tarifas_viejas (liga_id, posicion, monto_centavos) "
        "SELECT t.liga_id, t.posicion, t.monto_centavos FROM tarifas t JOIN ligas l ON l.id = t.liga_id "
        "WHERE t.modalidad = COALESCE(l.modalidad, 'futbol_11')"
    )
    op.drop_table('tarifas')
    op.rename_table('tarifas_viejas', 'tarifas')
