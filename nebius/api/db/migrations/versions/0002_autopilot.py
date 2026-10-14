"""autopilot runs and their events

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14 09:00:00
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('autopilot_run',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('project_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('session_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('depth', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('text', sa.Text(), nullable=True),
    sa.Column('steps', sa.JSON(), nullable=True),
    sa.Column('result', sa.JSON(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.Column('finished_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('autopilot_run', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_autopilot_run_project_id'), ['project_id'], unique=False)

    op.create_table('autopilot_event',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('ts', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('autopilot_event', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_autopilot_event_run_id'), ['run_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('autopilot_event', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_autopilot_event_run_id'))
    op.drop_table('autopilot_event')
    with op.batch_alter_table('autopilot_run', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_autopilot_run_project_id'))
    op.drop_table('autopilot_run')
