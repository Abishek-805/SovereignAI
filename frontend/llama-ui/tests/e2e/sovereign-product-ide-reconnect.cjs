const {chromium}=require('playwright');const fs=require('node:fs');const path=require('node:path');
const out=path.resolve(__dirname,'../../../../outputs/product-verification-20261004');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const context=await browser.newContext({viewport:{width:1440,height:900}});const page=await context.newPage();
 try{
  const base='http://127.0.0.1:8088';
  const workspace=await(await context.request.post(base+'/coding/workspaces',{data:{name:'Product IDE reconnect '+Date.now()}})).json();
  await page.goto(base+'/#/');await page.getByRole('button',{name:'Code',exact:true}).click();
  await page.getByLabel('Open coding workspace').selectOption(workspace.workspace_id);
  await page.getByLabel('Code output').getByRole('button',{name:'Terminal',exact:true}).click();
  const terminal=page.getByRole('textbox',{name:'Terminal input'});
  await terminal.fill('python -c "import time; time.sleep(12); print(\'IDE_RECONNECT_OK\')"');
  const admission=page.waitForResponse(r=>r.url().endsWith('/jobs')&&r.request().method()==='POST');
  await terminal.press('Enter');const job=await(await admission).json();
  await page.waitForFunction(()=>localStorage.getItem('sovereign-code-job'));
  await context.setOffline(true);await page.waitForTimeout(3500);
  const preserved=await page.evaluate(()=>JSON.parse(localStorage.getItem('sovereign-code-job')||'null'));
  if(preserved?.job_id!==job.job_id)throw new Error('IDE discarded the disconnected job');
  await context.setOffline(false);await page.reload();
  await page.getByRole('button',{name:'Code',exact:true}).click();
  await page.getByLabel('Code output').locator('pre').getByText(/IDE_RECONNECT_OK/).waitFor({timeout:90000});
  await page.waitForFunction(()=>!localStorage.getItem('sovereign-code-job'));
  const final=await(await context.request.get(base+'/coding/jobs/'+job.job_id)).json();
  if(final.state!=='completed'||final.result.exit_code!==0||final.result.stdout.trim()!=='IDE_RECONNECT_OK')throw new Error('Restored IDE job failed');
  fs.writeFileSync(path.join(out,'ide-reconnect.json'),JSON.stringify({job_id:job.job_id,preserved,final,backend_task_restarted:false},null,2));
  await page.screenshot({path:path.join(out,'ide-reconnect.png')});
  console.log('IDE disconnected, retained same job, reloaded and displayed actual Docker output');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
