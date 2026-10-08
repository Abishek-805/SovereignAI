const {chromium}=require('playwright');const fs=require('node:fs');const path=require('node:path');
const base='http://127.0.0.1:8088';const out=path.resolve(__dirname,'../../../../outputs/agent-kernel-rebuild/browser-'+Date.now());fs.mkdirSync(out,{recursive:true});
const save=(name,value)=>fs.writeFileSync(path.join(out,name+'.json'),JSON.stringify(value,null,2));
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const context=await browser.newContext({viewport:{width:1440,height:900}});const page=await context.newPage();
 const api=async(url,body)=>{const response=await context.request.fetch(base+url,{method:body?'POST':'GET',data:body,timeout:240000});if(!response.ok())throw new Error(await response.text());return response.json()};
 try{
  let ready=false;for(let i=0;i<60;i++){try{ready=(await context.request.get(base+'/health',{timeout:1000})).ok()}catch{}if(ready)break;await page.waitForTimeout(500)}if(!ready)throw new Error('Backend did not become ready');
  const workspace=await api('/coding/workspaces',{name:'Native kernel browser '+Date.now()});const wid=workspace.workspace_id;
  const unrelated={'BinarySearch.java':'class BinarySearch { static int unchanged(){return 17;} }\n','unrelated.txt':'valuable user data\n','old_config.json':'{"preserve":true}\n'};
  for(const [name,content] of Object.entries(unrelated)){const response=await context.request.put(base+'/coding/workspaces/'+wid+'/files/'+name,{data:{content}});if(!response.ok())throw new Error(await response.text())}
  await page.goto(base+'/#/',{waitUntil:'domcontentloaded',timeout:120000});await page.evaluate(wid=>localStorage.setItem('sovereign-active-workspace',wid),wid);await page.reload({waitUntil:'domcontentloaded',timeout:120000});
  await page.getByRole('navigation',{name:'Primary workbench navigation'}).getByRole('button',{name:'Agent',exact:true}).click();
  await page.getByRole('button',{name:'Project context',exact:true}).click();
  await page.getByRole('group',{name:'Select project'}).getByRole('button',{name:workspace.name,exact:true}).click();
  const goal='Create a small Flask attendance application.\n\nRequirements:\n- Python Flask\n- store students\n- POST attendance endpoint\n- reject invalid attendance requests\n- return JSON responses\n- include README.md\n- application must be runnable\n- include a simple test';
  const knowledge=page.getByLabel('Local agent').getByRole('switch',{name:'Connect Knowledge'});if(await knowledge.getAttribute('aria-checked')==='true')await knowledge.click();
  const input=page.getByRole('textbox',{name:'Task request'});await input.fill(goal);
  const admission=page.waitForResponse(r=>r.url().endsWith('/agent/jobs')&&r.request().method()==='POST',{timeout:60000});
  await page.getByRole('button',{name:'Send task',exact:true}).click();const response=await admission;const admitted=await response.json();const submitted=JSON.parse(response.request().postData());save('admission',{request:submitted,response:admitted});
  if(submitted.workspace_id!==wid)throw new Error('Submission does not target the isolated QA workspace');
  let final;for(let i=0;i<900;i++){final=await api('/coding/jobs/'+admitted.job_id);if(final.state!=='running')break;await page.waitForTimeout(1000)}
  save('final',final);if(final.state!=='completed')throw new Error('Agent failed: '+JSON.stringify({job_id:final.job_id,state:final.state,error:final.error,completion:final.completion,evidence:out}));
  const actual=final.result.workspace_id||final.result.result?.workspace_id||wid;if(actual!==wid)throw new Error('Selected workspace identity changed');
  await page.getByRole('button',{name:'Accept changes',exact:true}).last().waitFor({timeout:30000});await page.screenshot({path:path.join(out,'ready-for-review.png')});
  const acceptance=page.waitForResponse(r=>r.url().endsWith('/accept')&&r.request().method()==='POST');await page.getByRole('button',{name:'Accept changes',exact:true}).last().click();if(!(await acceptance).ok())throw new Error('Acceptance failed');
  const state=await api('/coding/workspaces/'+actual);save('accepted-workspace',state);
  if(actual!==wid)throw new Error('Selected workspace identity changed');
  for(const [name,content] of Object.entries(unrelated)){const file=await api('/coding/workspaces/'+actual+'/files/'+name);if(file.content!==content)throw new Error('Unrelated file changed: '+name)}
  save('preservation',{workspace_id:actual,files:Object.keys(unrelated),passed:true});
  console.log('Actual SovereignAI Agent -> native tools -> Docker -> UI review -> Accept PASS; '+out);
 }finally{await browser.close()}
})().catch(error=>{save('error',{error:String(error),stack:error.stack});console.error(error);process.exitCode=1});
