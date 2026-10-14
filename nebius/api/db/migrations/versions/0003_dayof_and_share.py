"""day-of observations (N07) and read-only share links (N09)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-14 22:00:00
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('live_observation',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('project_id', sa.String(), nullable=False),
    sa.Column('kind', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.Column('data', sa.JSON(), nullable=True),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.Column('updated_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['project.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('live_observation', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_live_observation_project_id'), ['project_id'], unique=False)

    # only the SHA-256 of a share token is stored; the token itself is shown once
    op.create_table('share_link',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('project_id', sa.String(), nullable=False),
    sa.Column('session_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('token_sha256', sa.String(), nullable=False),
    sa.Column('label', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.Column('expires_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.Column('revoked_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['project.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_sha256')
    )
    with op.batch_alter_table('share_link', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_share_link_project_id'), ['project_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('share_link', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_share_link_project_id'))
    op.drop_table('share_link')
    with op.batch_alter_table('live_observation', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_live_observation_project_id'))
    op.drop_table('live_observation')
