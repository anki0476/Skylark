import asyncio
import json
import time
import threading
import uuid
from copy import deepcopy
from decimal import Decimal
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from skylark.wind.api import create_app
from skylark.wind.db import Database, events, runs
from skylark.wind.domain import RunSpec, Policy, Final, canonical
from skylark.wind.provider import Settings
from skylark.wind.runner import Context, run_live, work_once
from skylark.wind.service import enqueue, propose, compare
from skylark.wind.replay import replay_record
from skylark.wind.reporting import report


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / 'lab')


def completed(db, spec=None):
    ident = enqueue(db, spec or RunSpec(), uuid.uuid4().hex)
    work_once(db, run_id=ident)
    return ident


@pytest.mark.parametrize('mutation', ['response', 'effect', 'delivered', 'request', 'guard', 'fault', 'call_count'])
def test_replay_rejects_changed_tool_transcript(db, mutation):
    ident = completed(db, RunSpec(policy=Policy(stable_key=True,reconcile=True,validate_receipt=True)))
    row, trace = deepcopy(db.get(ident)), deepcopy(db.read_events(ident))
    if mutation == 'call_count':
        row['result']['tool_calls'] += 1
        trace[-1]['payload'] = row['result']
    elif mutation == 'effect':
        trace.pop(next(i for i,e in enumerate(trace) if e['kind']=='tool_effect'))
    else:
        kind = {'response':'tool_observed','delivered':'agent_observed','request':'tool_requested','guard':'runtime_guard','fault':'tool_observed'}[mutation]
        event = next(e for e in trace if e['kind']==kind and (mutation!='fault' or e['payload'].get('fault')))
        if mutation in ('response','delivered'):
            event['payload']['result']={'status':'invented'}
        elif mutation=='request':
            event['payload']['arguments']['resource']='other-room'
        elif mutation=='guard':
            event['payload']['operation_key']='another-intent'
        else:
            event['payload']['fault']='incomplete_response'
    for sequence,event in enumerate(trace,1):
        event['sequence']=sequence
    with pytest.raises(ValueError):
        replay_record(row,trace)


def test_regression_validates_source_before_executing_tools(db):
    ident = completed(db)
    damaged = next(e for e in db.read_events(ident) if e['kind']=='agent_observed')
    damaged['payload']['result']={'status':'invented'}
    with db.transaction() as connection:
        connection.execute(update(events).where(events.c.id==damaged['id']).values(payload=canonical(damaged['payload'])))
    regression = enqueue(db,RunSpec(mode='regression',source_run_id=ident),'damaged-source-regression')
    work_once(db,run_id=regression)
    assert db.get(regression)['status']=='failed'
    assert not any(e['kind']=='tool_requested' for e in db.read_events(regression))


def fake_provider(decisions):
    class Provider:
        def __init__(self,*args,**kwargs):self.index=0
        def complete(self,*args):
            value=decisions[self.index];self.index+=1
            return {'message':{'role':'assistant','tool_calls':[{'id':str(self.index),'function':value}]}}
    return Provider


def test_malformed_json_counts_as_a_rejected_tool_invocation(db):
    ident=enqueue(db,RunSpec(),'bad-json-proposal');db.claim('owner')
    context=Context(db,ident,'owner',RunSpec())
    provider=fake_provider([{'name':'create_reservation','arguments':'{bad'},
        {'name':'finish','arguments':'{"status":"incomplete"}'}])
    result=run_live(context,Settings('fixture',Decimal(1),Decimal(3),Decimal(2)),provider)
    assert result.status=='incomplete' and context.calls==1
    assert not context.sandbox.state['reservations']
    rejected=next(e for e in db.read_events(ident) if e['kind']=='tool_observed')
    assert rejected['payload']['result']['error']=='invalid_tool_or_arguments'


def test_internal_tool_failure_is_not_reclassified_as_bad_arguments(db,monkeypatch):
    ident=enqueue(db,RunSpec(),'internal-failure');db.claim('owner')
    context=Context(db,ident,'owner',RunSpec())
    calls=[]
    def fail(*args,**kwargs):
        calls.append(1)
        raise ValueError('Persistence failed after execution')
    monkeypatch.setattr(context,'call',fail)
    provider=fake_provider([{'name':'create_reservation','arguments':'{}'}, {'name':'finish','arguments':'{"status":"incomplete"}'}])
    with pytest.raises(ValueError,match='Persistence failed'):
        run_live(context,Settings('fixture',Decimal(1),Decimal(3),Decimal(2)),provider)
    assert len(calls)==1


def test_scoped_report_reads_only_scoped_records_and_usage(db):
    from skylark.wind.benchmark import schedule
    protocol=schedule(db,trials=1,split='development')
    other=completed(db)
    charge=db.reserve(other,100,1000);db.settle(charge,100,{'private':'outside scope'})
    # A malformed unrelated snapshot must not be deserialized by a scoped query.
    with db.transaction() as connection:
        connection.execute(update(runs).where(runs.c.id==other).values(snapshot='invalid unrelated data'))
    result=report(db,protocol['id'])
    assert {r['run_id'] for r in result['attempts']}==set(protocol['runs'])
    assert result['usage_attempts']==[]
    assert result['budget']['accounted_usd']==.0001  # Clearly global project allowance.


def test_summary_omits_details_and_uses_database_indexes(db):
    ident=completed(db)
    usage=db.reserve(ident,100,1000)
    with TestClient(create_app(db)) as client:
        status=client.get('/api/v1/status').json()
        assert status['queue']=={'queued':0,'running':0}
        assert 'attempts' not in status['budget']
        summary=client.get('/api/v1/results').json()
        assert summary['detail_level']=='summary' and 'attempts' not in summary
        full=client.get('/api/v1/results/export').json()
        assert full['usage_attempts'][0]['id']==usage
    with db.engine.connect() as connection:
        plans=[str(row) for row in connection.exec_driver_sql('EXPLAIN QUERY PLAN SELECT * FROM events WHERE run_id=? AND sequence>? ORDER BY sequence',(ident,0))]
        assert any('ix_events_run_sequence' in row for row in plans)


@pytest.mark.parametrize('cursor',['-1','nope',str(2**80)])
def test_invalid_reconnect_cursor_has_a_visible_client_error(db,cursor):
    ident=completed(db)
    with TestClient(create_app(db)) as client:
        assert client.get(f'/api/v1/runs/{ident}/events',headers={'Last-Event-ID':cursor}).status_code==422
        assert client.get(f'/api/v1/runs/{ident}/events?after={cursor}').status_code==422


def test_event_stream_does_not_block_async_requests(db,monkeypatch):
    ident=completed(db)
    original=db.read_events
    progress=threading.Event()
    observations=[]
    def slow_read(*args,**kwargs):
        time.sleep(.15)
        observations.append(progress.is_set())
        return original(*args,**kwargs)
    monkeypatch.setattr(db,'read_events',slow_read)
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(db)),base_url='http://testserver') as client:
            async def heartbeat():
                await asyncio.sleep(.03);progress.set()
            response,_=await asyncio.gather(client.get(f'/api/v1/runs/{ident}/events?stream=true'),heartbeat())
            assert response.status_code==200
    asyncio.run(exercise())
    assert observations and all(observations)


def test_repair_of_maximum_length_version_remains_executable(db):
    ident=completed(db,RunSpec(agent_version='a'*100))
    proposal=propose(db,ident);db.approve(proposal['id'])
    pair=compare(db,proposal['id'])['pairs'][0]
    while work_once(db):pass
    assert db.get(pair['after'])['status']=='completed'
    assert len(db.get(pair['after'])['snapshot']['spec']['agent_version'])<=100


def test_live_repair_description_uses_catalogue_without_model_spend(db,monkeypatch):
    settings=Settings('nvidia/mock',Decimal(1),Decimal(3),Decimal(2))
    ident=completed(db)
    snapshot=db.get(ident)['snapshot']
    snapshot['spec']['mode']='live';snapshot['model']=settings.snapshot()
    with db.transaction() as connection:
        connection.execute(update(runs).where(runs.c.id==ident).values(snapshot=canonical(snapshot)))
    monkeypatch.setattr(Settings,'load',lambda:settings)
    proposal=propose(db,ident)
    assert proposal['payload']['provenance']=='deterministic_catalogue'
    assert 'Fresh comparison runs are needed' in proposal['payload']['explanation']
    assert not db.budget()['attempts']


def test_batch_projection_rounds_each_request_up(db,monkeypatch):
    from skylark.wind.benchmark import schedule
    # Each maximum request is 0.26048 microdollars before integer rounding.
    settings=Settings('nvidia/mock',Decimal('.00001'),Decimal('.00001'),Decimal('.0001'))
    monkeypatch.setattr(Settings,'load',lambda:settings)
    with pytest.raises(ValueError,match='exceeds'):
        schedule(db,mode='live',trials=1,split='development')
    assert not db.list_runs() and not db.budget()['attempts']


def test_limited_live_held_out_protocol_fits_current_allowance_before_queueing(db,monkeypatch):
    from skylark.wind.benchmark import schedule
    configured = Settings('nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B',
                          Decimal('0.06'), Decimal('0.24'), Decimal('0.50'))
    monkeypatch.setattr(Settings, 'load', lambda: configured)
    protocol = schedule(db, mode='live', split='held_out', trials=1,
                        cases_per_fault=1, freshness_guard=True)
    assert len(protocol['runs']) == 12
    assert all(db.get(run_id)['snapshot']['model'] == configured.snapshot()
               for run_id in protocol['runs'])
    assert all(db.get(run_id)['snapshot']['spec']['scenario']['task_message']
               for run_id in protocol['runs'][2:4])
    monkeypatch.setattr(Settings, 'load', lambda: Settings(
        configured.model, configured.input_rate, configured.output_rate, Decimal('0.36')))
    with pytest.raises(ValueError, match='exceeds'):
        schedule(db, mode='live', split='held_out', trials=1,
                 cases_per_fault=1, freshness_guard=True)
    assert len(db.list_runs()) == 12


@pytest.mark.parametrize('allowance,permitted',[('.00002',False),('.00004',True)])
def test_live_comparison_budget_uses_exact_integer_bounds(db,monkeypatch,allowance,permitted):
    settings=Settings('nvidia/mock',Decimal('.00001'),Decimal('.00001'),Decimal(allowance))
    ident=completed(db)
    snapshot=db.get(ident)['snapshot']
    snapshot['spec']['mode']='live';snapshot['model']=settings.snapshot()
    with db.transaction() as connection:
        connection.execute(update(runs).where(runs.c.id==ident).values(snapshot=canonical(snapshot)))
    monkeypatch.setattr(Settings,'load',lambda:settings)
    repair=db.save_repair(ident,{'kind':'runtime','after':Policy(stable_key=True).model_dump()})
    db.approve(repair['id'])
    if permitted:
        assert len(compare(db,repair['id'])['pairs'])==1
    else:
        with pytest.raises(ValueError,match='exceeds'):
            compare(db,repair['id'])
    assert not db.budget()['attempts']


def test_index_upgrade_preserves_existing_evidence(db):
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    import skylark.wind.db as module
    ident=completed(db)
    original=db.get(ident)
    config=Config();config.set_main_option('script_location',str(Path(module.__file__).parent/'migrations'))
    with db.transaction() as connection:
        config.attributes['connection']=connection
        command.downgrade(config,'0001_agent_lab')
    db.engine.dispose()
    migrated=Database(db.directory)
    assert migrated.get(ident)==original
    assert replay_record(migrated.get(ident),migrated.read_events(ident))['matches_recorded']
    with migrated.engine.connect() as connection:
        assert connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='0002_query_indexes'
