const {chromium}=require('playwright'),fs=require('node:fs'),path=require('node:path');
const out=path.resolve(__dirname,'../../../../outputs/build-contract-product/'+(process.env.QA_ARM||'browser-v2'));fs.mkdirSync(out,{recursive:true});
const cases=[
['files','Create main.py, helpers.py and README.md. helpers.answer() must return 42.'],
['temperature','Create a Python CLI accepting --temperature 25 and reject negative values.'],
['flask','Create a Flask API with /health returning 200.'],
['node','Create a Node HTTP service on port 3000 with /health returning 200.'],
['java','Create a Java CLI that prints 42.'],
['preserve','Create main.py and helpers.py, helpers.answer() must return 42. Preserve keep.txt unchanged.'],
['repair','Fix the intentional error in helpers.py so helpers.answer() must return 42. Create main.py importing answer and printing it, and README.md. Preserve keep.txt unchanged.'],
['bounded','Create main.py, helpers.py and README.md, helpers.answer() must return 42. Do not create unrelated files.']];
const transfers=JSON.parse(fs.readFileSync(process.env.QA_FIXTURES||path.resolve(__dirname,'../../../../outputs/build-contract-product/acceptance-fixtures.json'),'utf8'));
if(process.env.QA_TRANSFER)for(const test of transfers)cases.push([test.id,test.request]);
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:900}});const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 try {
  for(const [id,goal] of cases.filter(([id])=>!process.env.QA_CASES||process.env.QA_CASES.split(',').includes(id))){
   const destination=path.join(out,id+'.json');if(fs.existsSync(destination))continue;
   const w=await (await page.request.post('http://127.0.0.1:8088/coding/workspaces',{data:{name:'Contract QA '+id+' '+Date.now()}})).json();
   if(['preserve','repair'].includes(id))await page.request.put(`http://127.0.0.1:8088/coding/workspaces/${w.workspace_id}/files/keep.txt`,{data:{content:'PRESERVE ORIGINAL\n'}});
   if(id==='repair')await page.request.put(`http://127.0.0.1:8088/coding/workspaces/${w.workspace_id}/files/helpers.py`,{data:{content:'def answer():\n    raise ValueError("intentional fixture error")\n'}});
   const supplied=transfers.find(test=>test.id===id);
   if(supplied)await page.request.put(`http://127.0.0.1:8088/coding/workspaces/${w.workspace_id}/files/test_acceptance.py`,{data:{content:supplied.acceptance}});
   await page.goto('http://127.0.0.1:8088/#/');
   await page.getByRole('navigation',{name:'Primary workbench navigation'}).getByRole('button',{name:'Agent',exact:true}).click();
   const agent=page.getByRole('region',{name:'Local agent'});const sw=agent.getByRole('switch',{name:'Connect Knowledge'});
   await agent.getByRole('button',{name:'New chat',exact:true}).click();
   if(await sw.getAttribute('aria-checked')==='true')await sw.click();
   await agent.getByRole('button',{name:'Project context',exact:true}).click();
   await agent.getByRole('group',{name:'Select project'}).getByRole('button',{name:w.name,exact:true}).click();
   await agent.getByRole('textbox',{name:'Task request',exact:true}).fill(goal);
   const responsePromise=page.waitForResponse(r=>r.url().endsWith('/agent/jobs')&&r.request().method()==='POST');
   const started=Date.now();await agent.getByRole('button',{name:'Send task',exact:true}).click();const response=await responsePromise;
   const admission=await response.json();const evidence={id,goal,workspace_id:w.workspace_id,request:JSON.parse(response.request().postData()),admission,status:'INCOMPLETE'};
   fs.writeFileSync(destination,JSON.stringify(evidence,null,2));
   if(admission.job_id){for(let n=0;n<900;n++){
    evidence.final=await(await page.request.get('http://127.0.0.1:8088/coding/jobs/'+admission.job_id)).json();evidence.latency_ms=Date.now()-started;
    fs.writeFileSync(destination,JSON.stringify(evidence,null,2));if(evidence.final.state!=='running')break;await page.waitForTimeout(1000);
   }}
   evidence.status=evidence.final?.state==='completed'?'COMPLETED_REQUIRES_AUDIT':'FAIL';evidence.page_errors=errors.slice();
   fs.writeFileSync(destination,JSON.stringify(evidence,null,2));await page.screenshot({path:path.join(out,id+'.png'),fullPage:true});
   console.log(id,evidence.final?.state,evidence.final?.error||evidence.final?.result?.answer);
  }
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
