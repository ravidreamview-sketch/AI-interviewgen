"""Create tutor_sessions and tutor_messages tables for Phase 3 AI Tutor Agent

Revision ID: 0004_tutor_sessions
Revises: 0003_adaptive_learning_path
Create Date: 2026-11-20 15:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0004_tutor_sessions'
down_revision: Union[str, None] = '0003_adaptive_learning_path'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tutor_sessions',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('session_id', sa.String(length=64), unique=True, nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user_accounts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('roadmap_id', sa.String(length=64), nullable=True, index=True),
        sa.Column('activity_id', sa.String(length=64), nullable=True, index=True),
        sa.Column('concept', sa.String(length=255), nullable=False),
        sa.Column('teaching_mode', sa.String(length=50), nullable=False, server_default='explain'),
        sa.Column('complexity_level', sa.String(length=50), nullable=False, server_default='standard'),
        sa.Column('skill_level', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('title', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )

    op.create_table(
        'tutor_messages',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('session_id', sa.Integer(), sa.ForeignKey('tutor_sessions.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('code_snippet', sa.Text(), nullable=True),
        sa.Column('pedagogical_intent', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('tutor_messages')
    op.drop_table('tutor_sessions')
