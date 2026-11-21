"""Create agent_execution_metrics and agent_workflow_runs tables for Phase 7

Revision ID: 0007_agent_orchestration_monitoring
Revises: 0006_project_mentoring
Create Date: 2026-11-20 18:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0007_agent_orchestration_monitoring'
down_revision: Union[str, None] = '0006_project_mentoring'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agent_execution_metrics',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('execution_id', sa.String(length=64), unique=True, nullable=False, index=True),
        sa.Column('agent_id', sa.String(length=64), nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user_accounts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('workflow_id', sa.String(length=64), nullable=True, index=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='completed'),
        sa.Column('latency_ms', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('tokens_prompt', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tokens_completion', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cost_estimate_usd', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, index=True),
    )

    op.create_table(
        'agent_workflow_runs',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('workflow_id', sa.String(length=64), unique=True, nullable=False, index=True),
        sa.Column('workflow_type', sa.String(length=64), nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user_accounts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('steps_completed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_steps', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('result_summary', sa.Text(), nullable=True),
        sa.Column('error_details', sa.Text(), nullable=True),
        sa.Column('idempotency_key', sa.String(length=128), nullable=True, index=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, index=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('agent_workflow_runs')
    op.drop_table('agent_execution_metrics')
