"""Create learner_projects and project_mentorship_turns tables for Phase 5

Revision ID: 0006_project_mentoring
Revises: 0005_real_world_scenarios
Create Date: 2026-11-20 16:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0006_project_mentoring'
down_revision: Union[str, None] = '0005_real_world_scenarios'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'learner_projects',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('project_id', sa.String(length=64), unique=True, nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user_accounts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('target_role', sa.String(length=255), nullable=False),
        sa.Column('domain', sa.String(length=100), nullable=False, server_default='Full-Stack Web Systems'),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('architecture_overview', sa.Text(), nullable=True),
        sa.Column('tech_stack', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='planning'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )

    op.create_table(
        'project_mentorship_turns',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('project_id', sa.String(length=64), sa.ForeignKey('learner_projects.project_id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user_accounts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('mentorship_stage', sa.String(length=50), nullable=False),
        sa.Column('user_query', sa.Text(), nullable=False),
        sa.Column('mentor_guidance', sa.Text(), nullable=False),
        sa.Column('action_items', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('project_mentorship_turns')
    op.drop_table('learner_projects')
