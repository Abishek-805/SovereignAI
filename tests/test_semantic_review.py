import json
import pytest
from backend.model import LocalModel
from backend.contracts import WorkbenchError


def completion(value):
    return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}]}


def model_replies(monkeypatch, replies):
    model=LocalModel(verify_semantics=True)
    calls=[]
    sequence=iter([{'task_interpretation':'Preserve the original task and its constraints'},*replies])
    def request(method,path,**kwargs):
        calls.append(kwargs['json'])
        return completion(next(sequence))
    monkeypatch.setattr(model,'_request',request)
    return model,calls


def test_semantic_review_repairs_request_contradiction_once(monkeypatch):
    model,calls=model_replies(monkeypatch,[{'action':'edit','path':'other.py'},
        {'verdict':'revise','issues':['User requested selected.py; proposed path is other.py']},
        {'action':'edit','path':'selected.py'},{'verdict':'accept','issues':[]}])
    result=model._planned_completion({'model':'sovereign-code','messages':[{'role':'user','content':'Update selected.py only'}],'max_tokens':512})
    assert json.loads(result['choices'][0]['message']['content'])['path']=='selected.py'
    assert len(calls)==5
    assert all(call['model']=='sovereign-code' for call in calls)
    assert 'validation_feedback' in calls[3]['messages'][-1]['content']


def test_unresolved_semantics_abstains_after_one_repair(monkeypatch):
    model,calls=model_replies(monkeypatch,[{'answer':'unsupported claim'},
        {'verdict':'revise','issues':['Candidate claim has no supplied evidence']},
        {'answer':'still unsupported'}, {'verdict':'revise','issues':['Still no source support']}])
    with pytest.raises(WorkbenchError) as error:
        model._planned_completion({'messages':[{'role':'user','content':'Use the attached evidence'}],'max_tokens':512})
    assert error.value.code=='semantic_uncertainty'
    assert len(calls)==5


def test_missing_information_clarifies_without_repair(monkeypatch):
    model,calls=model_replies(monkeypatch,[{'answer':'guess'}, {'verdict':'clarify','issues':['No conversion unit was supplied']}])
    with pytest.raises(WorkbenchError):
        model._planned_completion({'messages':[{'role':'user','content':'Convert the measurement'}],'max_tokens':512})
    assert len(calls)==3


def test_vision_reviewer_receives_actual_image(monkeypatch):
    model,calls=model_replies(monkeypatch,[{'answer':'visible title'}, {'verdict':'accept','issues':[]}])
    image={'type':'image_url','image_url':{'url':'data:image/png;base64,fixture'}}
    model._planned_completion({'messages':[{'role':'user','content':[image,{'type':'text','text':'Read the title'}]}],'max_tokens':512})
    content=calls[2]['messages'][-1]['content']
    assert content[0]==image
    assert 'base64' not in content[-1]['text']


def test_three_turn_refinement_retains_literal_rule_and_initial_measure(monkeypatch):
    model=LocalModel()
    base={'operation':'percentage','outcome':'pass','followup':False,'threshold':None,'threshold_operator':'none','rule_outcome':'other','score_columns':['Score'],'result_values':[],'entity_values':['GROUP'],'scope':'all','assessments':[]}
    rule={**base,'followup':True,'threshold':18,'threshold_operator':'lt','rule_outcome':'fail','entity_values':[]}
    again={**base,'operation':'select','outcome':'other','followup':True,'entity_values':[]}
    again.update(operation='percentage',outcome='pass',entity_values=['GROUP'],threshold=18,threshold_operator='lt',rule_outcome='fail')
    replies=iter([again])
    monkeypatch.setattr(model,'_request',lambda *args,**kwargs:completion(next(replies)))
    query=model.plan_table_query('Show that report again',[{'id':'T1','sheet':'Exam','columns':['ID','Score']}],
        ['user: Pass percentage for GROUP in every exam','assistant: Untrusted wrong answer','user: Under 18 means failed'])
    intent=query['_measure']
    assert intent['operation']=='percentage' and intent['outcome']=='pass'
    assert intent['entity_values']==['GROUP']
    assert intent['threshold']==18 and intent['threshold_operator']=='lt' and intent['rule_outcome']=='fail'


def test_context_delta_changes_outcome_without_losing_rule(monkeypatch):
    model=LocalModel()
    base={'operation':'percentage','outcome':'pass','followup':False,'threshold':18,'threshold_operator':'lt','rule_outcome':'fail','score_columns':['Score'],'result_values':[],'entity_values':['GROUP'],'scope':'all','assessments':[]}
    changed={**base,'outcome':'fail','followup':True,'threshold':None,'entity_values':[]}
    changed.update(threshold=18,entity_values=['GROUP'])
    replies=iter([changed])
    monkeypatch.setattr(model,'_request',lambda *args,**kwargs:completion(next(replies)))
    query=model.plan_table_query('Instead the failing percentage under the same rule',[{'id':'T1','sheet':'Exam','columns':['ID','Score']}],
        ['user: Pass percentage for GROUP; under 18 fails'])
    assert query['_measure']['outcome']=='fail'
    assert query['_measure']['threshold']==18
    assert query['_measure']['entity_values']==['GROUP']


def test_interpretation_is_retained_in_proposal_review_and_repair(monkeypatch):
    model,calls=model_replies(monkeypatch,[{'outcome':'fail'},
        {'verdict':'revise','issues':['Original request still asks for passing percentage']},
        {'outcome':'pass'},{'verdict':'accept','issues':[]}])
    model._planned_completion({'messages':[{'role':'system','content':'Produce a contract'},
        {'role':'user','content':'Under 18 defines failure; update report'}],'max_tokens':512},
        task_context={'request':'Under 18 defines failure; update report','history':['user: Pass percentage for GROUP']})
    assert calls[0]['messages'][1]['content']=='Pass percentage for GROUP'
    assert 'Task interpretation' in calls[1]['messages'][0]['content']
    assert 'Task interpretation' in calls[2]['messages'][-1]['content']
    assert 'Task interpretation' in calls[3]['messages'][0]['content']

def test_literal_rule_resolution_ignores_wrong_assistant_report(monkeypatch):
    model=LocalModel(verify_semantics=True)
    wrong={'operation':'percentage','outcome':'pass','followup':True,'threshold':18,'threshold_operator':'lt','rule_outcome':'pass','score_columns':['Score'],'result_values':[],'entity_values':['GROUP'],'scope':'all','assessments':[]}
    monkeypatch.setattr(model,'_planned_completion',lambda *args,**kwargs:completion(wrong))
    seen=[]
    def resolve(*args,**kwargs):
        seen.append(kwargs['json'])
        result={'rule_outcome':'fail','threshold':18,'threshold_operator':'lt'}
        if len(seen)==1:result['outcome']='pass'
        return completion(result)
    monkeypatch.setattr(model,'_request',resolve)
    query=model.plan_table_query('Repeat that report',[{'id':'T1','sheet':'Exam','columns':['ID','Score']}],
        ['user: Pass percentage for GROUP','assistant: Incorrect: below 18 passes','user: Under 18 fails'])
    assert query['_measure']['rule_outcome']=='fail'
    assert query['_measure']['outcome']=='pass'
    assert 'Incorrect:' not in seen[0]['messages'][-1]['content']

def test_disagreeing_outcome_interpretations_require_clarification(monkeypatch):
    model=LocalModel(verify_semantics=True)
    proposal={'operation':'percentage','outcome':'pass','followup':True,'threshold':18,'threshold_operator':'lt','rule_outcome':'fail','score_columns':['Score'],'result_values':[],'entity_values':[],'scope':'all','assessments':[]}
    monkeypatch.setattr(model,'_planned_completion',lambda *args,**kwargs:completion(proposal))
    monkeypatch.setattr(model,'_request',lambda *args,**kwargs:completion({'outcome':'fail','rule_outcome':'fail','threshold':18,'threshold_operator':'lt'}))
    with pytest.raises(WorkbenchError) as error:
        model.plan_table_query('Use the new rule',[{'id':'T1','sheet':'Exam','columns':['Score']}],['user: Pass percentage','user: Under 18 fails'])
    assert error.value.code=='needs_input'
    assert 'passing or failing' in str(error.value)
