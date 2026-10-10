from rag.tables import bind_selection_request,execute_query
from rag.answer import _query_presentation

def test_comparison_preserves_absent_identity_and_separate_measurements():
 table={'name':'Scores','columns':['Member','Exam A','Exam B'],'records':[
  {'Member':'TEAM001','Exam A':24,'Exam B':30},
  {'Member':'TEAM051','Exam A':25,'Exam B':20}]}
 plan={'table':'T1','operation':'select','columns':table['columns'],
       'filters':[{'column':'Member','operator':'in','value':['TEAM001','TEAM051']}]}
 plan=bind_selection_request(plan,table,'Compare TEAM001,TEAM051,TEAM063 and tell who did better; 25 is the pass mark.')
 result=execute_query(table,plan)
 assert result['missing_entities']==['TEAM063']
 assert result['comparison']['pass_counts']==[
  {'identity':'TEAM001','passed':1,'assessments':2},
  {'identity':'TEAM051','passed':1,'assessments':2}]
 assert result['comparison']['field_maxima'][0]['identities']==['TEAM051']
 assert result['comparison']['field_maxima'][1]['identities']==['TEAM001']
 rendered=_query_presentation([{'label':'S1','query_result':result}])
 assert 'TEAM063' in rendered and 'No matching source record' in rendered
 assert 'Exam A: TEAM051' in rendered and 'Exam B: TEAM001' in rendered

def test_plain_selection_does_not_infer_ranking_or_pass_threshold():
 table={'name':'Items','columns':['ID','Value'],'records':[{'ID':'A1','Value':7}]}
 plan=bind_selection_request({'operation':'select','columns':['ID','Value'],'filters':[{'column':'ID','operator':'eq','value':'A1'}]},table,'Show A1')
 result=execute_query(table,plan)
 assert 'comparison' not in result and 'pass_threshold' not in plan

def test_zero_padded_id_requires_unambiguous_source_binding():
 table={'name':'Scores','columns':['ID','Score'],'records':[{'ID':'TEAM063','Score':42}]}
 plan={'operation':'select','columns':['ID','Score'],'filters':[{'column':'ID','operator':'eq','value':'TEAM63'}]}
 bound=bind_selection_request(plan,table,'Compare TEAM63 and TEAM64')
 assert bound['entity_bindings']=={}
 assert execute_query(table,bound)['missing_entities']==['TEAM63','TEAM64']
 table['records'].append({'ID':'TEAM0063','Score':20})
 assert bind_selection_request(plan,table,'Compare TEAM63')['entity_bindings']=={}

def test_app_entrypoint_and_helpers_have_distinct_completion_contracts():
 from workflows.source_quality import application_entrypoint_issue,source_issue
 source='def add(a,b):\n return a+b\n'
 assert source_issue('helpers.py',source) is None
 assert application_entrypoint_issue('calculator.py',source)
 assert application_entrypoint_issue('calculator.py',source+'\nif __name__ == "__main__":\n print(add(2,3))\n') is None
 assert application_entrypoint_issue('server.py','from flask import Flask\napp=Flask(__name__)\n') is None

def test_reverification_preserves_installed_dependency_image(tmp_path,monkeypatch):
 import json
 from types import SimpleNamespace
 from backend import desktop
 image='sha256:'+'a'*64
 (tmp_path/'sandbox-validation.json').write_text(json.dumps({'image_id':image}))
 calls=[]
 def run(command,**kwargs):
  calls.append(command)
  return SimpleNamespace(returncode=0,stdout=image if 'inspect' in command else json.dumps({'normal_execution':True}))
 monkeypatch.setattr(desktop.subprocess,'run',run)
 monkeypatch.setattr('router.sandbox._docker_cli',lambda:'docker')
 result=desktop.verify_docker(tmp_path,SimpleNamespace(progress=lambda message:None))
 assert calls[0][5]==image
 assert result['image_id']==image
