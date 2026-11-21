"""Create real_world_scenarios and scenario_submissions tables for Phase 4

Revision ID: 0005_real_world_scenarios
Revises: 0004_tutor_sessions
Create Date: 2026-11-20 16:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0005_real_world_scenarios'
down_revision: Union[str, None] = '0004_tutor_sessions'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'real_world_scenarios',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('scenario_id', sa.String(length=64), unique=True, nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user_accounts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('domain', sa.String(length=100), nullable=False),
        sa.Column('target_role', sa.String(length=255), nullable=False),
        sa.Column('difficulty', sa.String(length=50), nullable=False, server_default='Intermediate'),
        sa.Column('difficulty_level', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('context', sa.Text(), nullable=False),
        sa.Column('problem_statement', sa.Text(), nullable=False),
        sa.Column('required_skills', sa.Text(), nullable=False),
        sa.Column('objectives', sa.Text(), nullable=False),
        sa.Column('instructions', sa.Text(), nullable=False),
        sa.Column('constraints', sa.Text(), nullable=False),
        sa.Column('deliverables', sa.Text(), nullable=False),
        sa.Column('rubric', sa.Text(), nullable=False),
        sa.Column('success_criteria', sa.Text(), nullable=False),
        sa.Column('hints', sa.Text(), nullable=True),
        sa.Column('is_completed', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )

    op.create_table(
        'scenario_submissions',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('submission_id', sa.String(length=64), unique=True, nullable=False, index=True),
        sa.Column('scenario_id', sa.String(length=64), sa.ForeignKey('real_world_scenarios.scenario_id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user_accounts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('solution_text', sa.Text(), nullable=False),
        sa.Column('code_submission', sa.Text(), nullable=True),
        sa.Column('architectural_notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='evaluated'),
        sa.Column('overall_score', sa.Float(), nullable=True),
        sa.Column('dimension_scores', sa.Text(), nullable=True),
        sa.Column('strengths', sa.Text(), nullable=True),
        sa.Column('areas_for_improvement', sa.Text(), nullable=True),
        sa.Column('evidence', sa.Text(), nullable=True),
        sa.Column('feedback', sa.Text(), nullable=True),
        sa.Column('recommended_next_steps', sa.Text(), nullable=True),
        sa.Column('evaluation_disclaimer', sa.Text(), nullable=True),
        sa.Column('evaluated_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('scenario_submissions')
    op.drop_table('real_world_scenarios')
