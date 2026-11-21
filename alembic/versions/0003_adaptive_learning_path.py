"""Create adaptive_roadmaps table for Phase 2 Adaptive Learning Path Agent

Revision ID: 0003_adaptive_learning_path
Revises: 0002_learner_profile
Create Date: 2026-11-20 15:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0003_adaptive_learning_path'
down_revision: Union[str, None] = '0002_learner_profile'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'adaptive_roadmaps',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('roadmap_id', sa.String(length=64), unique=True, nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user_accounts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('target_role', sa.String(length=255), nullable=False),
        sa.Column('target_level', sa.String(length=50), nullable=False, server_default='Mid-Level'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
        sa.Column('overall_progress', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('total_estimated_hours', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('completed_activities_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_activities_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('roadmap_data', sa.Text(), nullable=False),
        sa.Column('adaptation_history', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('adaptive_roadmaps')
