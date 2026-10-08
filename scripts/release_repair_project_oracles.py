"""Live QA fixtures and independent Docker oracles; no generated host execution."""
import json,time,hashlib,os
from pathlib import Path
from scripts.full_qa_inventory import http
OUT=Path('outputs/release-repair')
def save(name,r):
 p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():p.rename(p.with_name(p.stem+'-'+str(time.time_ns())+p.suffix))
 p.write_text(json.dumps(r,indent=2),encoding='utf-8')
def idle():
 for _ in range(1200):
  r=http('/status')['body']
  if not r.get('busy') and not r.get('active_jobs'):return
  time.sleep(1)
 raise RuntimeError('Existing job still active; no interference')
def job(path,payload):
 idle();ad=http(path,'POST',payload);assert ad['status']==200,ad
 jid=ad['body']['job_id']
 for _ in range(900):
  r=http('/coding/jobs/'+jid)['body']
  if r['state']!='running':return {'admission':ad,'final':r}
  time.sleep(1)
 raise RuntimeError('Job exceeded QA observation window')
def staged(value):
 if isinstance(value,dict):
  if value.get('publication_state')=='staged' and value.get('state')=='completed':return value
  for child in value.values():
   found=staged(child)
   if found:return found
 if isinstance(value,list):
  for child in value:
   found=staged(child)
   if found:return found
 return None
idle()
cases=[('AT-13',{'helpers.py':'def answer():\n    return 41\n','main.py':'from helpers import answer\nprint(answer())\n','test_oracle.py':'import unittest\nimport helpers\nclass Oracle(unittest.TestCase):\n def test_answer(self):self.assertEqual(helpers.answer(),42)\n'},'Update helpers.py so answer() returns integer 42, and update main.py to import answer and print answer(). Run main.py and verify exactly 42.'),('AT-14',{'notes.txt':'QA_PRESERVE_SENTINEL\n','test_oracle.py':'import unittest\nfrom helpers import answer\nclass Oracle(unittest.TestCase):\n def test_answer(self):self.assertEqual(answer(),42)\n'},'Keep notes.txt byte-for-byte unchanged. Create helpers.py defining answer() returning integer 42, and main.py importing answer and printing answer(). Run it and verify 42.'),('AT-20',{'notes.txt':'QA_PRESERVE_SENTINEL\n','division.py':'def divide(a,b):\n    return a/0\n\ndef invoice_total(items):\n    return sum(items)\n\nif __name__ == "__main__":\n    print(divide(6,2))\n','test_oracle.py':'import unittest\nfrom division import divide, invoice_total\nclass Oracle(unittest.TestCase):\n def test_normal(self):self.assertEqual(divide(6,2),3)\n def test_zero(self):\n  with self.assertRaises(ValueError):divide(6,0)\n def test_invoice(self):self.assertEqual(invoice_total([5,7]),12)\n'},'Repair division.py using the actual ZeroDivisionError: divide(a,b) must return a/b for nonzero b and raise ValueError for b=0. Preserve invoice_total(items), notes.txt, and test_oracle.py exactly. Run and verify all tests and the program.')]
for case,files,goal in cases:
 if os.getenv('QA_CASES') and case not in os.getenv('QA_CASES').split(','):continue
 idle();w=http('/coding/workspaces','POST',{'name':'Release oracle '+case+' '+str(time.time_ns())})['body']['workspace_id'];r={'id':case,'workspace_id':w,'goal':goal,'fixture':files}
 for name,content in files.items():assert http('/coding/workspaces/'+w+'/files/'+name,'PUT',{'content':content})['status']==200
 if case=='AT-20':r['baseline_failure']=job('/coding/workspaces/'+w+'/jobs',{'kind':'run','target':'division.py'})
 r['agent']=job('/agent/jobs',{'goal':goal,'workspace_id':w,'document_ids':[],'history':[]});save('agent/'+case+'-oracle.json',r)
 draft=staged(r['agent'])
 if draft:
  r['draft_id']=draft['task_id'];r['accept']=http('/coding/workspaces/'+w+'/tasks/'+draft['task_id']+'/accept','POST',{})
  if r['accept']['status']==200:
   r['independent_oracle']=job('/coding/workspaces/'+w+'/jobs',{'kind':'terminal','command':'python -m unittest -v test_oracle'})
   entry='division.py' if case=='AT-20' else 'main.py';r['program']=job('/coding/workspaces/'+w+'/jobs',{'kind':'run','target':entry})
   protected={name:content for name,content in files.items() if name in {'notes.txt','test_oracle.py'}}
   r['preserved']={name:http('/coding/workspaces/'+w+'/files/'+name)['body'].get('content')==content for name,content in protected.items()}
   run=r['program']['final'].get('result',{});oracle=r['independent_oracle']['final'].get('result',{})
   r['status']='PASS' if r['agent']['final']['state']=='completed' and oracle.get('exit_code')==0 and run.get('exit_code')==0 and all(r['preserved'].values()) and ('42' in run.get('stdout','') if case!='AT-20' else '3.0' in run.get('stdout','')) else 'FAIL'
 else:r['status']='FAIL'
 save('agent/'+case+'-oracle.json',r);print(case,r['status'],flush=True)
