"""Create learner_profiles table for Phase 1 Learner Intelligence

Revision ID: 0002_learner_profile
Revises: 0001_initial_schema
Create Date: 2026-11-20 14:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0002_learner_profile'
down_revision: Union[str, None] = '0001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'learner_profiles',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user_accounts.id', ondelete='CASCADE'), unique=True, nullable=False, index=True),
        sa.Column('target_role', sa.String(length=255), nullable=False, server_default='Full-Stack Engineer'),
        sa.Column('secondary_roles', sa.Text(), nullable=True),
        sa.Column('career_goals', sa.Text(), nullable=True),
        sa.Column('target_level', sa.String(length=50), nullable=False, server_default='Mid-Level'),
        sa.Column('education_level', sa.String(length=100), nullable=True),
        sa.Column('institution', sa.String(length=255), nullable=True),
        sa.Column('graduation_year', sa.Integer(), nullable=True),
        sa.Column('years_of_experience', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('current_role', sa.String(length=255), nullable=True),
        sa.Column('current_company', sa.String(length=255), nullable=True),
        sa.Column('preferred_learning_goals', sa.Text(), nullable=True),
        sa.Column('career_interests', sa.Text(), nullable=True),
        sa.Column('self_reported_skills', sa.Text(), nullable=True),
        sa.Column('latest_scan_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('learner_profiles')
