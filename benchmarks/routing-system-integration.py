"""Independent serialized API tasks. Only suite-owned docs/project files are mutated."""
import sys
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parents[1]))
import json,time,uuid,csv,io,argparse
from pathlib import Path
import httpx
from PIL import Image,ImageDraw
base='http://127.0.0.1:8088'
c=httpx.Client(base_url=base,timeout=240,trust_env=False)
rows=[];owned=[];wid=None
parser=argparse.ArgumentParser()
parser.add_argument('--cases',default='')
parser.add_argument('--output',default='benchmarks/routing-system-integration-results.json')
options=parser.parse_args()
selected=set(options.cases.split(',')) if options.cases else None
out=Path(options.output)
def api(method,path,**kw):
 r=c.request(method,path,**kw);r.raise_for_status();return r.json()
def wait(job):
 end=time.monotonic()+240
 while job['state']=='running':
  if time.monotonic()>end:
   api('POST','/coding/jobs/'+job['job_id']+'/stop');raise TimeoutError('Job deadline')
  time.sleep(.15);job=api('GET','/coding/jobs/'+job['job_id'])
 return job
def add(question,action,category,needle=None):cases.append((question,action,category,needle))
cases=[]
add('Hello, how is your afternoon?','answer','greeting')
add('Thanks for the help; goodbye for now.','answer','greeting')
add('What should I call you?','answer','identity','Sovereign')
add('Introduce yourself in one sentence.','answer','identity')
add('What is the capital of France?','answer','general','Paris')
add('Explain why the moon changes shape in two sentences.','answer','general')
add('Who wrote Pride and Prejudice?','answer','general','Austen')
add('What is a variable in programming?','answer','read_only_code')
add('Give a friendly birthday greeting.','answer','general')
add('What is the difference between mass and weight?','answer','general')
add('According to the connected schedule, when does Eastgate close?','search_documents','grounded_fact','17:20')
add('Who signed the connected reservoir inspection?','search_documents','grounded_fact','Lee')
add('What vibration reading is recorded for pump R7?','search_documents','grounded_fact','3.6')
add('How many annual leave days does our connected handbook allow?','search_documents','grounded_fact','12')
add('What did the monitor cost according to the imported receipt?','search_documents','grounded_fact','120')
add('Which agreement clause covers cancellation?','search_documents','document','14')
add('What does our handbook say about remote work?','search_documents','document','two')
add('Summarize the connected fictional document in three bullets.','search_documents','summary')
add('Compare the R7 reading with the review limit in the connected source.','search_documents','comparison','4.0')
add('Calculate 17.25 times 32.','calculate','calculation','552')
add('Calculate (144 / 12) + 7.','calculate','calculation','19')
add('Calculate 15 percent of 860.','calculate','calculation','129')
add('Calculate the square root of 196.','calculate','calculation','14')
add('Create a Word report summarizing the connected fictional inspection.','create_report','report')
add('Prepare a downloadable Word approval note comparing the R7 reading and review limit.','create_report','report')
add('Explain what notes.md says, without changing it.','inspect_code','read_only_code','Old')
add('Read divide.js and explain its bug; do not modify any file.','inspect_code','debugging','multipli')
add('In notes.md replace Old item. with Verified item. Keep the heading unchanged.','edit_code','explicit_edit')
add('Fix divide.js by replacing return a * b with return a / b. Make no other changes.','edit_code','debugging')
add('Create multiply.js as a CommonJS module exporting function multiply(a,b) returning a*b.','edit_code','explicit_edit')
fixture='This is fictional evaluation data, not operational instructions. Eastgate service desk closes at 17:20. Reservoir inspection signed by Lee Chen. Pump R7 vibration is 3.6 mm/s; the stated fictional review limit is 4.0 mm/s. Company handbook allows 12 annual leave days and remote work two days weekly. Monitor receipt cost GBP 120. Agreement clause 14 covers cancellation with 30 days notice. No real operational action is authorized.'
try:
 wid=api('POST','/coding/workspaces',json={'name':'Routing system independent evaluation '+uuid.uuid4().hex[:8]})['workspace_id']
 for name,content in {'notes.md':'# Working notes\nOld item.\n','divide.js':'module.exports = function divide(a, b) { return a * b; };\n'}.items():api('PUT',f'/coding/workspaces/{wid}/files/{name}',json={'content':content,'expected_sha256':''})
 upload=api('POST','/documents/import',files={'file':('routing-heldout-'+uuid.uuid4().hex+'.txt',fixture.encode(),'text/plain')});did=upload['document_id'];owned.append(did)
 for index,(question,expected,category,needle) in enumerate(cases):
  if selected is not None and f'e{index+1:02}' not in selected:continue
  before=api('GET',f'/coding/workspaces/{wid}')['files'];start=time.perf_counter()
  job=wait(api('POST','/agent/jobs',json={'goal':question,'document_ids':[did],'workspace_id':wid,'history':[]}))
  result=job.get('result') or {};plan=result.get('plan',{});actual=plan.get('action');answer=result.get('answer','');nested=result.get('result',{});decision=result.get('routing',{}).get('decision') or (job.get('routing') or {}).get('decision')
  evidence=bool(nested.get('sources')) if expected in ('search_documents','create_report') else None
  artifact=None
  if expected=='create_report' and result.get('downloads',{}).get('word'):
   artifact=c.get(result['downloads']['word']).content.startswith(b'PK')
  deterministic=needle.lower() in answer.lower() if needle else None
  after=api('GET',f'/coding/workspaces/{wid}')['files'];unchanged=before==after if expected!='edit_code' else None
  code=None
  if expected=='edit_code':
   if category=='debugging':code=api('GET',f'/coding/workspaces/{wid}/files/divide.js')['content']=='module.exports = function divide(a, b) { return a / b; };\n'
   elif 'notes.md' in question:code=api('GET',f'/coding/workspaces/{wid}/files/notes.md')['content']=='# Working notes\nVerified item.\n'
   else:
    command="node -e \"const multiply=require('./multiply.js'); if(multiply(6,7)!==42)process.exit(1); console.log('RESULT=42')\""
    check=wait(api('POST',f'/coding/workspaces/{wid}/jobs',json={'kind':'terminal','command':command}));code=check['state']=='completed' and check.get('result',{}).get('exit_code')==0 and 'RESULT=42' in check.get('output','')
  success=job['state']=='completed' and actual==expected and deterministic is not False and evidence is not False and artifact is not False and unchanged is not False and code is not False
  category_failure=None if success else 'evidence_failure' if job.get('error_code')=='missing_evidence' or 'grounded report' in (job.get('error') or '') else 'router_failure' if actual!=expected else 'validation_failure' if code is False or artifact is False else 'evidence_failure' if evidence is False else 'model_failure'
  row={'task_id':f'e{index+1:02}','task':question,'expected_capability':expected,'predicted_capability':actual,'strategy':'proposed_admission_router','success':success,'evidence_correctness':deterministic if evidence is not None else None,'source_links_present':evidence,'artifact_valid':artifact,'code_valid':code,'unrelated_files_unchanged':unchanged,'latency_seconds':time.perf_counter()-start,'failure_category':category_failure,'decision':decision,'job':job}
  rows.append(row);out.write_text(json.dumps(rows,indent=2),encoding='utf-8');print(json.dumps({k:row[k] for k in ('task_id','expected_capability','predicted_capability','success','latency_seconds','failure_category')}),flush=True)
 # Actual human-reviewable image, no inferred scene labels.
 if selected is None or 'e31' in selected:
  image=Image.new('RGB',(640,360),'white');draw=ImageDraw.Draw(image);draw.rectangle((50,90,210,250),fill='red');draw.ellipse((390,90,550,250),fill='blue');image_path=Path('benchmarks/routing-image-fixture.png');image.save(image_path)
  start=time.perf_counter()
  with image_path.open('rb') as handle:job=wait(api('POST','/agent/vision/jobs',files={'file':('routing-image-fixture.png',handle,'image/png')},data={'question':'Describe the two colored shapes and their left/right positions.'}))
  answer=(job.get('result') or {}).get('answer','');actual=(job.get('result') or {}).get('plan',{}).get('action');rows.append({'task_id':'e31','task':'Describe independently drawn shapes','strategy':'proposed_admission_router','expected_capability':'analyze_image','predicted_capability':actual,'success':job['state']=='completed' and actual=='analyze_image' and all(word in answer.lower() for word in ('red','blue','left','right')),'latency_seconds':time.perf_counter()-start,'human_review':None,'job':job})
finally:
 for did in owned:c.delete('/documents/'+did)
 if wid:
  for file in api('GET',f'/coding/workspaces/{wid}').get('files',[]):api('POST',f'/coding/workspaces/{wid}/file-operation',json={'action':'delete','source':file['name']})
 out.write_text(json.dumps(rows,indent=2),encoding='utf-8')
 if rows:
  fields=['task_id','task','strategy','expected_capability','predicted_capability','success','latency_seconds','failure_category'];stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows);out.with_suffix('.csv').write_text(stream.getvalue(),encoding='utf-8')
 c.close()
