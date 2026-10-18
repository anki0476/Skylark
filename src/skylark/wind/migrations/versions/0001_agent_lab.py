"""Frozen initial agent-lab schema, independent of future application metadata."""
from alembic import op

revision = "0001_agent_lab"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute('\nCREATE TABLE comparisons (\n\tid VARCHAR NOT NULL, \n\tpayload TEXT NOT NULL, \n\tcreated FLOAT NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n')
    op.execute('\nCREATE TABLE events (\n\tid VARCHAR NOT NULL, \n\trun_id VARCHAR NOT NULL, \n\tsequence INTEGER NOT NULL, \n\tkind VARCHAR NOT NULL, \n\tpayload TEXT NOT NULL, \n\tcreated FLOAT NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n')
    op.execute('CREATE INDEX ix_events_run_id ON events (run_id)')
    op.execute('\nCREATE TABLE reconciliations (\n\tid VARCHAR NOT NULL, \n\tattempt_id VARCHAR NOT NULL, \n\tpayload TEXT NOT NULL, \n\tcreated FLOAT NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n')
    op.execute('\nCREATE TABLE repairs (\n\tid VARCHAR NOT NULL, \n\trun_id VARCHAR NOT NULL, \n\tpayload TEXT NOT NULL, \n\tapproved INTEGER NOT NULL, \n\tcreated FLOAT NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n')
    op.execute('\nCREATE TABLE runs (\n\tid VARCHAR NOT NULL, \n\trequest_key VARCHAR NOT NULL, \n\trequest_hash VARCHAR NOT NULL, \n\tsnapshot TEXT NOT NULL, \n\tstatus VARCHAR NOT NULL, \n\tcreated FLOAT NOT NULL, \n\tupdated FLOAT NOT NULL, \n\towner VARCHAR, \n\tcancel_requested INTEGER NOT NULL, \n\tresult TEXT, \n\tstate TEXT, \n\terror TEXT, \n\tsequence INTEGER NOT NULL, \n\tartifact_bytes INTEGER NOT NULL, \n\tcomparison_id VARCHAR, \n\tPRIMARY KEY (id), \n\tUNIQUE (request_key)\n)\n\n')
    op.execute('\nCREATE TABLE usage (\n\tid VARCHAR NOT NULL, \n\trun_id VARCHAR NOT NULL, \n\treserved_micros INTEGER NOT NULL, \n\taccounted_micros INTEGER NOT NULL, \n\tstatus VARCHAR NOT NULL, \n\tpayload TEXT NOT NULL, \n\tcreated FLOAT NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n')
    op.execute('\nCREATE TABLE workers (\n\tid INTEGER NOT NULL, \n\towner VARCHAR, \n\texpires FLOAT NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n')


def downgrade():
    op.drop_table('workers')
    op.drop_table('usage')
    op.drop_table('runs')
    op.drop_table('repairs')
    op.drop_table('reconciliations')
    op.drop_table('events')
    op.drop_table('comparisons')
