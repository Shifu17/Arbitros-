"""comprobante de pago de equipos

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-02 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('abonos_equipos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('comprobante', sa.String(length=255), nullable=True))

    with op.batch_alter_table('cobros_equipos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('comprobante', sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('cobros_equipos', schema=None) as batch_op:
        batch_op.drop_column('comprobante')

    with op.batch_alter_table('abonos_equipos', schema=None) as batch_op:
        batch_op.drop_column('comprobante')
