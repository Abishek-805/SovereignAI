"""Fixed, independently checked model-generated projects; never handwrite candidates."""
import argparse,json,time,hashlib
from pathlib import Path
from scripts.full_qa_inventory import http
from router.sandbox import CodeSandbox

CASES=[
 {'id':'inventory','request':'Create a runnable Python inventory CLI application in main.py and stock.py using only the standard library. stock.py defines reserve(stock, item, quantity): return a new dictionary with quantity removed, preserve the input dictionary, raise KeyError for unknown items and ValueError for negative quantities or insufficient stock. main.py imports reserve and accepts ITEM QUANTITY arguments against initial stock apple=10, pear=4, prints the remaining quantity, and exits nonzero with a useful error on invalid requests. Do not modify existing files.',
  'oracle':'''from stock import reserve
s={'apple':10,'pear':4}
assert reserve(s,'apple',3)=={'apple':7,'pear':4} and s['apple']==10
for args,kind in [(('banana',1),KeyError),(('apple',-1),ValueError),(('pear',5),ValueError)]:
 try:reserve(s,*args)
 except kind:pass
 else:raise AssertionError('Required exception not raised')
run(['apple','3'],'7');run(['pear','4'],'0');run(['banana','1'],None)
'''},
 {'id':'temperature','request':'Build a runnable Python temperature converter application in main.py and conversion.py, standard library only. conversion.py exports convert(value, source, target) supporting C, F and K, including identical units, and raises ValueError for unknown units or temperatures below absolute zero. main.py imports convert and accepts VALUE SOURCE TARGET arguments, prints the converted numeric result and exits nonzero for invalid input. Leave existing unrelated files unchanged.',
  'oracle':'''from conversion import convert
assert abs(convert(0,'C','F')-32)<1e-8
assert abs(convert(32,'F','K')-273.15)<1e-8
assert convert(100,'C','C')==100
for args in [(1,'X','C'),(-274,'C','K'),(-1,'K','C')]:
 try:convert(*args)
 except ValueError:pass
 else:raise AssertionError('Invalid unit/temperature accepted')
run(['0','C','F'],'32');run(['-1','K','C'],None)
'''},
 {'id':'text_report','request':'Make a runnable Python text-report CLI project with main.py and analysis.py, no external dependencies. analysis.py exports summarize(text), returning a dictionary with words (whitespace-separated), characters (including whitespace), and lines (splitlines count; empty input has zero lines). main.py imports summarize, reads a UTF-8 file given as its only argument and prints that dictionary as JSON. Missing files must produce a nonzero exit and useful message. Preserve existing unrelated files.',
  'oracle':'''from analysis import summarize
assert summarize('one two\\nthree')=={'words':3,'characters':13,'lines':2}
assert summarize('')=={'words':0,'characters':0,'lines':0}
Path('sample.txt').write_text('one two\\nthree',encoding='utf-8')
p=run(['sample.txt'],None,expected_code=0)
assert json.loads(p.stdout)=={'words':3,'characters':13,'lines':2}
run(['missing.txt'],None)
'''}]

SEED='def unrelated(value):\n    return value * 17\n'
def project_result(value):
 if isinstance(value,dict):
  if 'changes' in value and 'operation_plan' in value:return value
  for key in ('result','operations'):
   found=project_result(value.get(key))
   if found:return found
 elif isinstance(value,list):
  for item in reversed(value):
   found=project_result(item)
   if found:return found
 return {}

def run_case(case,out,arm):
 w=http('/coding/workspaces','POST',{'name':f'Understanding QA {arm} {case["id"]} {time.time_ns()}'})['body']['workspace_id']
 http('/coding/workspaces/'+w+'/files/unrelated.py','PUT',{'content':SEED})
 if case.get('acceptance'):
  http('/coding/workspaces/'+w+'/files/test_acceptance.py','PUT',{'content':case['acceptance']})
 request={'workspace_id':w,'document_ids':[],'goal':case['request'],'history':[
  'User: Create Java linear and binary search programs in array_search.',
  'Assistant: Search project finished.','User: Explain the previous calculator project.','Assistant: The calculator adds numbers.']}
 admission=http('/agent/jobs','POST',request)
 evidence={'arm':arm,'case':case,'workspace_id':w,'request':request,'admission':admission,'status':'INCOMPLETE'}
 dest=out/(case['id']+'.json')
 if admission['status']!=200:
  evidence['status']='BLOCKED';dest.write_text(json.dumps(evidence,indent=2),encoding='utf-8');return evidence
 start=time.monotonic()
 for _ in range(600):
  final=http('/coding/jobs/'+admission['body']['job_id'])['body'];evidence['final']=final
  dest.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
  if final.get('state')!='running':break
  time.sleep(1)
 evidence['latency']=time.monotonic()-start
 result=project_result(final.get('result'))
 changes=result.get('changes',[])
 candidates={c['path']:c['after'].encode() for c in changes if c.get('action') in {'create','edit'}}
 evidence['candidate_sha256']={k:hashlib.sha256(v).hexdigest() for k,v in candidates.items()}
 evidence['preserved_unrelated']=http('/coding/workspaces/'+w+'/files/unrelated.py')['body'].get('content')==SEED and not any(c['path']=='unrelated.py' for c in changes)
 if case.get('acceptance'):
  evidence['preserved_acceptance']=http('/coding/workspaces/'+w+'/files/test_acceptance.py')['body'].get('content')==case['acceptance'] and not any(c['path']=='test_acceptance.py' for c in changes)
 if candidates:
  wrapper='''import sys,shutil,subprocess,json,os
from pathlib import Path
root=Path('/output/project');shutil.copytree('/input',root,ignore=lambda s,n:{'program.py'})
os.chdir(root);sys.path.insert(0,str(root))
def run(args,expected,expected_code=None):
 p=subprocess.run([sys.executable,'main.py',*args],capture_output=True,text=True,timeout=5)
 if expected_code==0 or expected is not None:
  assert p.returncode==0,(p.stdout,p.stderr)
  if expected is not None:assert expected in p.stdout,p.stdout
 else:assert p.returncode!=0 and (p.stderr.strip() or p.stdout.strip()),'Missing useful error'
 return p
'''+case['oracle']+"\nprint('INDEPENDENT_ORACLE_PASS')\n"
  image=http('/workbench/info')['body']['sandbox']['image_id']
  r=CodeSandbox('docker',image).execute(wrapper,input_files=candidates)
  evidence['oracle']={'executed':r.executed,'exit_code':r.exit_code,'stdout':r.stdout,'stderr':r.stderr}
  evidence['status']='PASS' if r.executed and r.exit_code==0 and evidence['preserved_unrelated'] and evidence.get('preserved_acceptance',True) and final.get('state')=='completed' else 'FAIL'
 else:evidence['status']='FAIL' if final.get('state')=='failed' else 'BLOCKED'
 dest.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
 print(case['id'],evidence['status'],round(evidence['latency'],1),flush=True)
 return evidence

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('arm');args=parser.parse_args()
 out=Path('outputs/model-understanding')/args.arm;out.mkdir(parents=True,exist_ok=True)
 results=[]
 for case in CASES:
  if (out/(case['id']+'.json')).exists():raise RuntimeError('Preserve existing arm; choose a new label')
  results.append(run_case(case,out,args.arm))
 (out/'summary.json').write_text(json.dumps([{'id':r['case']['id'],'status':r['status'],'latency':r.get('latency')} for r in results],indent=2),encoding='utf-8')
