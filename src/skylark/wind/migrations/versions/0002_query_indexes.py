"""Indexes for the queue, report scopes, and reconnect event cursors."""
from alembic import op

revision = "0002_query_indexes"
down_revision = "0001_agent_lab"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('ix_events_run_sequence', 'events', ['run_id', 'sequence'], unique=True)
    op.drop_index('ix_events_run_id', table_name='events')
    op.create_index('ix_runs_status_created', 'runs', ['status', 'created'])
    op.create_index('ix_runs_comparison_created', 'runs', ['comparison_id', 'created'])
    op.create_index('ix_runs_created', 'runs', ['created'])
    op.create_index('ix_usage_run_id', 'usage', ['run_id'])


def downgrade():
    op.drop_index('ix_usage_run_id', table_name='usage')
    op.drop_index('ix_runs_created', table_name='runs')
    op.drop_index('ix_runs_comparison_created', table_name='runs')
    op.drop_index('ix_runs_status_created', table_name='runs')
    op.create_index('ix_events_run_id', 'events', ['run_id'])
    op.drop_index('ix_events_run_sequence', table_name='events')
