import threading
from rag.tables import bind_selection_request, execute_query
from rag.answer import _query_presentation

def test_lowest_request_renders_minimum_not_maximum():
    table = {'name':'Costs','columns':['ID','Cost'],'records':[
        {'ID':'PART01','Cost':'10'}, {'ID':'PART02','Cost':40}]}
    plan = bind_selection_request({'operation':'select','columns':table['columns'],
        'filters':[{'column':'ID','operator':'in','value':['PART01','PART02']}]},
        table, 'Compare PART01 and PART02: which has the lowest cost?')
    result = execute_query(table, plan)
    answer = _query_presentation([{'label':'S1','query_result':result}])
    assert 'Lowest recorded value' in answer
    assert 'Cost: PART01 (10)' in answer
    assert 'Most field leads' not in answer

def test_preview_switch_waits_for_active_interaction(monkeypatch,tmp_path):
    from workflows import preview_session as module
    entered=threading.Event();release=threading.Event();closed=threading.Event()
    class Session:
        def __init__(self,*args):self.closed=False;self.calls=0
        def close(self):closed.set();self.closed=True
        def request(self,payload):
            if payload.get('slow'):
                entered.set();assert release.wait(3)
            return {'ok':True}
    monkeypatch.setattr(module,'_sessions',{})
    monkeypatch.setattr(module,'PreviewSession',Session)
    errors=[]
    def invoke(key,payload):
        try:module.session_request(key,None,'',{},tmp_path/'state.db',payload)
        except Exception as exc:errors.append(exc)
    first=threading.Thread(target=invoke,args=('one',{'slow':True}))
    second=threading.Thread(target=invoke,args=('two',{}))
    first.start();assert entered.wait(2);second.start()
    try:premature=closed.wait(.2)
    finally:release.set();first.join(3);second.join(3)
    assert not premature, 'Switching previews closed an in-flight request'
    assert not first.is_alive() and not second.is_alive() and not errors


def test_compact_preview_cache_migrates_database_and_isolates_entrypoints(tmp_path):
    import hashlib,json
    from types import SimpleNamespace
    from workflows.web_preview import preview_request
    class Coding:
        def read(self,*args):return {}
        def raw_files(self,*args):return {'app.py':b'app', 'other.py':b'other'}
    files=Coding().raw_files()
    revision=hashlib.sha256(b''.join(name.encode()+b'\0'+data for name,data in sorted(files.items()))).hexdigest()
    legacy=tmp_path/'workspace'/revision/hashlib.sha256(b'app.py').hexdigest()/'state.db'
    legacy.parent.mkdir(parents=True);legacy.write_bytes(b'old-state')
    inputs=[]
    def execute(*args,**kwargs):
        inputs.append(kwargs['input_files'])
        return SimpleNamespace(exit_code=0,output_files={'web-response.json':json.dumps({'status':200,'body':'ok'}).encode()},stderr='')
    sandbox=SimpleNamespace(execute=execute)
    preview_request(Coding(),sandbox,tmp_path,'workspace','app.py')
    preview_request(Coding(),sandbox,tmp_path,'workspace','other.py')
    assert inputs[0]['__preview_state__.db']==b'old-state'
    assert '__preview_state__.db' not in inputs[1]
    assert legacy.read_bytes()==b'old-state'
    compact=tmp_path/'workspace'/hashlib.sha256((revision+'\0app.py').encode()).hexdigest()/'state.db'
    assert compact.read_bytes()==b'old-state'


def test_numeric_text_can_bind_an_explicit_outcome_rule():
    from rag.tables import compile_outcome_query
    table={'name':'Results','columns':['Group','Score'],'records':[
        {'Group':'A','Score':'30'}, {'Group':'A','Score':'10'}, {'Group':'A','Score':None}]}
    intent={'operation':'count','outcome':'pass','result_values':[],
        'entity_values':['A'],'entity_column':'Group','threshold':25,'threshold_operator':'gte',
        'score_columns':['Score'],'scope':'all'}
    query=compile_outcome_query(intent,{'T1':({'document_id':'d'},table)},'Count A passing records; pass mark is 25.')
    assert execute_query(table,query)['value']==1


def test_business_filter_order_does_not_hide_requested_identity():
    table={'name':'Scores','columns':['Group','ID','Score'],'records':[
        {'Group':'Red','ID':'TEAM001','Score':30},{'Group':'Red','ID':'TEAM051','Score':40}]}
    plan={'operation':'select','columns':table['columns'],'filters':[
        {'column':'Group','operator':'eq','value':'Red'},
        {'column':'ID','operator':'in','value':['TEAM001','TEAM051']}]}
    bound=bind_selection_request(plan,table,'Compare TEAM001, TEAM051 and TEAM063 in Red.')
    result=execute_query(table,bound)
    assert bound['identity_column']=='ID'
    assert result['missing_entities']==['TEAM063']
    assert {'column':'Group','operator':'eq','value':'Red'} in bound['filters']


def test_explicit_numeric_equality_does_not_depend_on_storage_type():
    from rag.tables import compile_outcome_query
    table={'name':'Data','columns':['Group','Score'],'records':[
        {'Group':'A','Score':25},{'Group':'A','Score':'25.0'},{'Group':'A','Score':26}]}
    intent={'operation':'count','outcome':'pass','result_values':[],
        'entity_values':['A'],'entity_column':'Group','threshold':None,'score_columns':[],'scope':'all'}
    plan=compile_outcome_query(intent,{'T':({'document_id':'d'},table)},'Count A records with Score equals 25.')
    assert execute_query(table,plan)['value']==2
    # Source-bound string identities retain literal equality and leading zeros.
    table={'name':'IDs','columns':['ID'],'records':[{'ID':'001'},{'ID':'1'}]}
    assert execute_query(table,{'operation':'count','columns':[],
        'filters':[{'column':'ID','operator':'eq','value':'001'}]})['value']==1
