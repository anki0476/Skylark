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
        def __init__(self,*args): pass
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
