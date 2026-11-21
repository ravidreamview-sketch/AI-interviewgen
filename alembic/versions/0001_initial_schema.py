"""Initial baseline schema migration

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-11-20 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Baseline schema captures pre-existing tables created via Base.metadata.create_all:
    # user_accounts, audit_logs, system_configs, interview_history, mock_interviews,
    # candidate_skill_analytics, candidate_mistakes_ledger, resume_scans, coach_sessions,
    # coach_messages, candidate_answer_attempts, user_invitations, rebuilt_resumes.
    pass


def downgrade() -> None:
    pass

