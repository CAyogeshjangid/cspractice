"""m18 generalize reminder_dispatch for dsc-expiry reminders

Additive + backward compatible: existing rows are calendar_row dispatches, so
subject_kind defaults to 'calendar_row' and reminder_config_id stays populated
for them. DSC dispatches set subject_kind='dsc_token' and dsc_token_id instead.

Revision ID: a1f2c3d4e5b6
Revises: 262fda290a37
Create Date: 2026-07-13 07:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1f2c3d4e5b6'
down_revision = '262fda290a37'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'reminder_dispatch',
        sa.Column('subject_kind', sa.String(length=20), nullable=False,
                  server_default='calendar_row'),
    )
    op.add_column(
        'reminder_dispatch',
        sa.Column('dsc_token_id', sa.UUID(), nullable=True),
    )
    op.alter_column('reminder_dispatch', 'reminder_config_id', nullable=True)
    op.create_foreign_key(
        'fk_reminder_dispatch_dsc_token', 'reminder_dispatch', 'dsc_token',
        ['dsc_token_id'], ['id'],
    )
    op.create_index(
        op.f('ix_reminder_dispatch_dsc_token_id'), 'reminder_dispatch',
        ['dsc_token_id'], unique=False,
    )
    # reminder_dispatch is a mutable table (status transitions); it keeps its
    # full CRUD grant. New columns inherit the table grant — no grant block.


def downgrade() -> None:
    op.drop_index(op.f('ix_reminder_dispatch_dsc_token_id'), table_name='reminder_dispatch')
    op.drop_constraint('fk_reminder_dispatch_dsc_token', 'reminder_dispatch', type_='foreignkey')
    op.alter_column('reminder_dispatch', 'reminder_config_id', nullable=False)
    op.drop_column('reminder_dispatch', 'dsc_token_id')
    op.drop_column('reminder_dispatch', 'subject_kind')
