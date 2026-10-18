import json
from decimal import Decimal
from types import SimpleNamespace
import httpx
import pytest
from openai import OpenAI
from skylark.wind.provider import Nebius, Settings, ProviderFailure
from skylark.wind.db import Database, BudgetExceeded
from skylark.wind.domain import RunSpec, Scenario, Fault, Final, freeze
from skylark.wind.runner import work_once, run_live, Context


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / 'lab')


def client(handler):
    return OpenAI(api_key='test-key-never-real',base_url='https://api.tokenfactory.nebius.com/v1/',max_retries=0,http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def settings(cap='2'):
    return Settings('nvidia/test-fixture',Decimal('1'),Decimal('3'),Decimal(cap))


def completion(arguments='{}',usage=True,reason='tool_calls'):
    result={'id':'fixture','object':'chat.completion','created':1,'model':'nvidia/test-fixture','choices':[{'index':0,'finish_reason':reason,'message':{'role':'assistant','content':None,'tool_calls':[{'id':'c1','type':'function','function':{'name':'finish','arguments':arguments}}]}}]}
    if usage: result['usage']={'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}
    return result


def test_reported_usage_and_no_hidden_retries(db):
    calls=[]
    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200,json=completion())
    response=Nebius(db,'run',settings(),client(handler)).complete([{'role':'user','content':'Test'}],[])
    assert response['message']['tool_calls']
    assert len(calls)==1
    assert db.budget()['accounted_usd']==.00016
    assert not db.budget()['uncertain_usd']


def test_timeout_keeps_reservation_and_never_retries(db):
    calls=[]
    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout('sensitive upstream text',request=request)
    with pytest.raises(ProviderFailure,match='no automatic'):
        Nebius(db,'run',settings(),client(handler)).complete([],[])
    assert len(calls)==1
    assert db.budget()['uncertain_usd']>0


def test_rate_limit_retries_once_and_accounts_both(db):
    calls=[]
    def handler(request):
        calls.append(1)
        if len(calls)==1:
            return httpx.Response(429,json={'error':{'message':'rate limit'}},headers={'Retry-After':'0'})
        return httpx.Response(200,json=completion())
    Nebius(db,'run',settings(),client(handler)).complete([],[])
    assert len(calls)==2
    assert len(db.budget()['attempts'])==2
    assert db.budget()['uncertain_usd']>0


@pytest.mark.parametrize('status',[401,402,403,500,503])
def test_provider_failures_not_retried_or_treated_as_free(db,status):
    calls=[]
    def handler(request):
        calls.append(1)
        return httpx.Response(status,json={'error':{'message':'do not reveal this response'}})
    with pytest.raises(ProviderFailure,match=f'HTTP {status}'):
        Nebius(db,'run',settings(),client(handler)).complete([],[])
    assert len(calls)==1 and db.budget()['uncertain_usd']>0


def test_missing_usage_stops(db):
    with pytest.raises(ProviderFailure,match='omitted usage'):
        Nebius(db,'run',settings(),client(lambda _:httpx.Response(200,json=completion(usage=False)))).complete([],[])
    assert db.budget()['uncertain_usd']>0


def test_budget_refusal_sends_no_request(db):
    calls=[]
    def handler(request):
        calls.append(1)
        return httpx.Response(200,json=completion())
    with pytest.raises(BudgetExceeded):
        Nebius(db,'run',settings('.000001'),client(handler)).complete([],[])
    assert not calls


def test_truncated_response_consumes_usage_but_not_success(db):
    result=Nebius(db,'run',settings(),client(lambda _:httpx.Response(200,json=completion(reason='length')))).complete([],[])
    assert result['invalid']=='truncated_or_refused'
    assert db.budget()['accounted_usd']>0


def test_tool_observations_never_include_authoritative_state(db):
    ident=db.enqueue(freeze(RunSpec()),'visible-observations')
    db.claim('owner')
    context=Context(db,ident,'owner',RunSpec())
    response=context.call('create_reservation',{'resource':'studio-a','customer':'Alex'})
    assert 'reservation_id' not in response and 'authoritative_result' not in response
    assert len(context.sandbox.state['reservations'])==1


def test_finish_batch_cannot_execute_side_effect(db):
    ident=db.enqueue(freeze(RunSpec()),'finish-batch')
    db.claim('owner')
    context=Context(db,ident,'owner',RunSpec())
    class Fake:
        def __init__(self,*args,**kwargs): pass
        def complete(self,*args):
            return {'message':{'role':'assistant','tool_calls':[
                {'id':'a','function':{'name':'create_reservation','arguments':'{"resource":"studio-a","customer":"Alex"}'}},
                {'id':'b','function':{'name':'finish','arguments':'{"status":"completed"}'}}]}}
    with pytest.raises(Exception,match='no tool'):
        run_live(context,settings(),Fake)
    assert not context.sandbox.state['reservations']


def test_allowance_gate(monkeypatch):
    for key,value in {'SKYLARK_LIVE_ENABLED':'1','NEBIUS_API_KEY':'test','NEBIUS_MODEL':'nvidia/test','NEBIUS_INPUT_USD_PER_MILLION':'1','NEBIUS_OUTPUT_USD_PER_MILLION':'3','SKYLARK_CONFIRMED_CREDITS_USD':'25','SKYLARK_ALLOWANCE_USD':'16'}.items():
        monkeypatch.setenv(key,value)
    with pytest.raises(ValueError,match='60%'):
        Settings.load()


@pytest.mark.parametrize('counts', [None, {}, {'prompt_tokens':None,'completion_tokens':2},
    {'prompt_tokens':-1,'completion_tokens':2}, {'prompt_tokens':2**40,'completion_tokens':2}])
def test_invalid_token_counts_preserve_uncertain_charge(db, counts):
    response = completion()
    response['usage'] = counts
    with pytest.raises(ProviderFailure, match='invalid counts'):
        Nebius(db,'run',settings(),client(lambda _:httpx.Response(200,json=response))).complete([],[])
    usage = db.budget()
    assert usage['uncertain_usd'] > 0
    assert usage['attempts'][0]['status'] == 'uncertain'
    assert usage['attempts'][0]['payload']['price_configuration']['id'] == 'nvidia/test-fixture'


def test_charge_above_estimate_pauses_spending_until_audited_resolution(db, monkeypatch):
    from skylark.wind.provider import readiness
    calls=[]
    def handler(request):
        calls.append(1)
        response=completion()
        if len(calls)==1:
            response['usage']={'prompt_tokens':50000,'completion_tokens':20,'total_tokens':50020}
        return httpx.Response(200,json=response)
    provider=Nebius(db,'run',settings(),client(handler))
    with pytest.raises(ProviderFailure,match='exceeded'):
        provider.complete([],[])
    before=db.budget()
    assert before['accounted_usd']==.05006 and len(before['unresolved_anomalies'])==1
    monkeypatch.setattr(Settings,'load',lambda:settings())
    assert not readiness(db)['enabled']
    with pytest.raises(BudgetExceeded,match='Spending paused'):
        provider.complete([],[])
    assert len(calls)==1
    db.resolve_anomaly(before['unresolved_anomalies'][0], 'Verified mock provider record and revised token ceiling; test-only evidence')
    assert db.budget()['accounted_usd']==before['accounted_usd']
    assert readiness(db)['enabled']
    provider.complete([],[])
    assert len(calls)==2 and not db.budget()['unresolved_anomalies']


@pytest.mark.parametrize('reason',['cancelled','expired'])
def test_fenced_or_cancelled_worker_cannot_start_billable_call(db,reason):
    from sqlalchemy import update
    from skylark.wind.db import workers, LeaseLost
    ident=db.enqueue(freeze(RunSpec()),'fenced-cost-'+reason)
    db.claim('old-owner')
    if reason=='cancelled':
        db.cancel(ident)
    else:
        with db.transaction() as connection:
            connection.execute(update(workers).values(expires=0))
    calls=[]
    provider=Nebius(db,ident,settings(),client(lambda request:calls.append(request)),owner='old-owner')
    with pytest.raises((BudgetExceeded,LeaseLost)):
        provider.complete([],[])
    assert not calls and not db.budget()['attempts']


@pytest.mark.parametrize('change,expected', [('duplicate','duplicate_call_identity'),('missing_arguments','malformed_message'),('missing_message','malformed_message')])
def test_malformed_decisions_are_invalid_and_accounted(db,change,expected):
    response=completion()
    if change=='duplicate':
        response['choices'][0]['message']['tool_calls'] *= 2
    elif change=='missing_arguments':
        del response['choices'][0]['message']['tool_calls'][0]['function']['arguments']
    else:
        response['choices'][0]['message']=None
    result=Nebius(db,'run',settings(),client(lambda _:httpx.Response(200,json=response))).complete([],[])
    assert result['invalid']==expected
    assert db.budget()['accounted_usd']==.00016


def test_expired_deadline_never_reserves_or_calls(db):
    calls=[]
    with pytest.raises(ProviderFailure,match='deadline exhausted'):
        Nebius(db,'run',settings(),client(lambda request:calls.append(request))).complete([],[],remaining=0)
    assert not calls and not db.budget()['attempts']


def test_reconciled_charge_above_estimate_also_pauses_spending(db):
    ident=db.reserve('stopped-run',100,10000)
    db.settle(ident,None,{'billing':'unconfirmed'})
    db.reconcile(ident,500,'Confirmed mock provider usage record for interrupted request')
    assert db.budget()['unresolved_anomalies']==[ident]
    with pytest.raises(BudgetExceeded,match='Spending paused'):
        db.reserve('another-run',100,10000)
