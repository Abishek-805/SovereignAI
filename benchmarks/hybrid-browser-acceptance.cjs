// Disposable real backend + built UI. Fixture staging/progress, no inference.
const {spawn}=require('node:child_process');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const crypto=require('node:crypto');
const {chromium}=require('../frontend/llama-ui/node_modules/playwright');
const base='http://127.0.0.1:8088',out=path.resolve(process.argv[2]||'benchmarks/hybrid-browser-acceptance');
const ensure=(value,message)=>{if(!value)throw Error(message)};
async function api(route,body){const response=await fetch(base+route,{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});const data=await response.json();ensure(response.ok,JSON.stringify(data));return data;}
const python=String.raw`
import json,sys,hashlib,difflib,os
sys.path.insert(0,os.getcwd())
print('Fixture imports starting',flush=True)
from pathlib import Path
import uvicorn
from backend.app import create_app
from backend.service import Workbench
from backend.settings import Settings
from router.model_registry import ModelRegistry
from backend.jobs import Job,Jobs
root=Path(sys.argv[1])
class Offline:
 def status(self):return {'available':False,'message':'Browser fixture: inference disabled'}
 def __getattr__(self,name):raise AssertionError('Model method forbidden: '+name)
service=Workbench(Settings(data_dir=root/'data',project_dir=root/'projects'),model=Offline(),registry=ModelRegistry(port=8097,specs={}))
print('Fixture Workbench created',flush=True)
first=service.coding.create('Browser selected workspace');second=service.coding.create('Browser other workspace')
before='def value():\n    return 1\n'.replace('\\n','\n');after=before.replace('return 1','return 2')
service.coding.write(first['workspace_id'],'demo.py',before)
service.coding.write(second['workspace_id'],'other.py','OTHER_WORKSPACE_MARKER = 1\n'.replace('\\n','\n'))
task=service.tasks.create('coding_workspace',[])
result={'task_id':task['task_id'],'workspace_id':first['workspace_id'],'target':'demo.py','state':'completed','changes':[{'action':'edit','path':'demo.py','before':before,'after':after}],'checks':{'container_executed':False,'target_committed':False},'validation':'fixture draft; no execution performed','diff':''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/demo.py',tofile='b/demo.py')),'output_files':[],'stdout':'','stderr':'','events':[]}
service.coding._stage_changes(first['workspace_id'],result,service.coding.raw_files(first['workspace_id']))
app=create_app(service)
jobs=next(cell.cell_contents for route in app.routes if getattr(route,'path','')=='/coding/jobs/{job_id}' for cell in route.endpoint.__closure__ if isinstance(cell.cell_contents,Jobs))
job=Job('edit');job.progress('Fixture public progress: checking selected workspace');job.preview('def value():\n    return 2\n'.replace('\\n','\n'),'code');jobs.jobs[job.id]=job
@app.get('/fixture/info')
def fixture():return {'workspace':first['workspace_id'],'other':second['workspace_id'],'task':task['task_id'],'job':job.id,'before':before,'fixture_only':True,'model_calls':0}
frontend=next(route for route in app.router.routes if getattr(route,'name',None)=='frontend')
app.router.routes.remove(frontend);app.router.routes.append(frontend)
uvicorn.run(app,host='127.0.0.1',port=8088,log_level='warning')
`;
(async()=>{
 await fs.mkdir(out,{recursive:true});const temp=await fs.mkdtemp(path.join(os.tmpdir(),'sovereign-browser-'));
 const launcher=path.join(temp,'launch.py');await fs.writeFile(launcher,python);
 const processHandle=spawn(path.resolve('.app-venv/Scripts/python.exe'),['-u',launcher,temp],{cwd:process.cwd(),env:{...process.env,PYTHONPATH:process.cwd()},windowsHide:true});
 let logs='';processHandle.stderr.on('data',data=>logs+=data);processHandle.stdout.on('data',data=>logs+=data);
 let browser;const report={fixtureOnly:true,modelCalls:0,dockerCalls:0,checks:[],pageErrors:[],limitations:['Synthetic draft and public preview fixture through real backend; no generated-code execution or live inference demonstrated.']};
 try{
  let ready=false;for(let i=0;i<240;i++){try{if((await fetch(base+'/fixture/info')).ok){ready=true;break;}}catch{}await new Promise(resolve=>setTimeout(resolve,250));}ensure(ready,'Backend startup failed: '+logs);
  const info=await api('/fixture/info');report.fixture=info;
  browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
  const context=await browser.newContext({viewport:{width:1600,height:1000},serviceWorkers:'block'}),page=await context.newPage();page.on('pageerror',error=>report.pageErrors.push(String(error)));report.networkErrors=[];page.on('requestfailed',request=>report.networkErrors.push({url:request.url(),failure:request.failure()}));page.on('console',message=>{if(message.type()==='error')report.networkErrors.push({console:message.text()});});
  await page.goto(base,{waitUntil:'domcontentloaded'});await page.getByRole('button',{name:'Code',exact:true}).click();
  await page.getByLabel('Open coding workspace').selectOption(info.workspace);await page.locator('.explorer-tree-area button[title="demo.py"]').waitFor();
  ensure(await page.locator('.explorer-tree-area button[title="other.py"]').count()===0,'Other workspace leaked into explorer');report.checks.push({name:'Selected workspace explorer scope',passed:true});
  await page.evaluate(info=>{localStorage.setItem('sovereign-active-workspace',info.workspace);window.dispatchEvent(new CustomEvent('sovereign-open-workspace',{detail:{tab:'code',taskId:info.task}}));},info);
  await page.locator('.source-diff').waitFor({timeout:30000});await page.getByRole('button',{name:'Accept changes',exact:true}).first().waitFor();
  const saved=await api(`/coding/workspaces/${info.workspace}/files/demo.py`),draft=await api(`/coding/workspaces/${info.workspace}/tasks/${info.task}`);
  ensure(saved.content===info.before,'Draft was automatically published');ensure(draft.publication_state==='staged'&&draft.checks.target_committed===false,'Draft lost staged status');ensure(draft.checks.container_executed===false,'Fixture falsely claimed Docker execution');
  report.checks.push({name:'Real staged API draft renders review; canonical bytes unchanged; no fake validation',passed:true});await page.screenshot({path:path.join(out,'staged-review.png')});
  await page.evaluate(info=>localStorage.setItem('sovereign-code-job',JSON.stringify({job_id:info.job,workspace_id:info.workspace,target:'demo.py'})),info);
  await page.reload({waitUntil:'domcontentloaded'});await page.getByRole('button',{name:'Code',exact:true}).click();
  await page.getByText('Fixture public progress: checking selected workspace',{exact:false}).first().waitFor({timeout:30000});
  await page.getByText('Draft code - not yet verified',{exact:true}).waitFor({timeout:30000});
  const body=await page.locator('body').innerText();ensure(body.includes('return 2'),'Public source preview not displayed');ensure(!body.includes('reasoning_content')&&!body.includes('chain_of_thought'),'Private reasoning field exposed');
  report.checks.push({name:'Real Job API public progress and code preview rendered from fixture',passed:true});await page.screenshot({path:path.join(out,'public-progress.png')});
  ensure((await api(`/coding/workspaces/${info.workspace}/files/demo.py`)).content===info.before,'Progress mutated canonical source');
  ensure(report.pageErrors.length===0,'Browser errors: '+report.pageErrors.join(';'));
  const built=await fs.readFile('frontend/llama-ui/dist/index.html');report.builtIndexSha256=crypto.createHash('sha256').update(built).digest('hex');report.passed=true;
 }catch(error){report.passed=false;report.error=String(error);if(browser){const page=browser.contexts()[0]?.pages()[0];if(page){await page.screenshot({path:path.join(out,'failure.png')}).catch(()=>{});report.visibleTail=(await page.locator('body').innerText()).slice(-6000);}}process.exitCode=1;}
 finally{if(browser)await browser.close();processHandle.kill();await new Promise(resolve=>processHandle.once('exit',resolve));report.backendLogs=logs;await fs.writeFile(path.join(out,'results.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));}
})();
