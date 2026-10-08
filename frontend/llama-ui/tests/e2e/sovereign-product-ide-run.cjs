const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const out=path.resolve(__dirname,'../../../../outputs/product-verification-20261004/ide-history-'+Date.now());
fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:900}});
 try {
  await page.goto('http://127.0.0.1:8088/#/');
  await page.evaluate(()=>{
   localStorage.setItem('sovereign-active-workspace','f2ac2ecf555048b6964e64eded90fc2e');
   localStorage.setItem('sovereign-code-history-f2ac2ecf555048b6964e64eded90fc2e',JSON.stringify([
    
    {jobId:'old-'+Math.random(),instruction:'run the todo app',target:'',at:Date.now(),answer:'Execution stopped because the continuation repeated an already attempted action. No successful application run was inferred.',state:'answered'},
    
    {jobId:'old-'+Math.random(),instruction:'run the todo app',target:'',at:Date.now(),answer:'Execution stopped because the continuation repeated an already attempted action. No successful application run was inferred.',state:'answered'}
   ]));
  });
  await page.getByRole('button',{name:'Code',exact:true}).click();
  await page.getByLabel('Open coding workspace').selectOption('f2ac2ecf555048b6964e64eded90fc2e');
  await page.getByLabel('Coding task',{exact:true}).fill('run the todo app');
  const admitted=page.waitForResponse(r=>r.url().endsWith('/agent/jobs')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Send',exact:true}).last().click();
  const response=await admitted; const job=await response.json();
  fs.writeFileSync(path.join(out,'ide-run-request.json'),response.request().postData());
  let final;
  for(let n=0;n<180;n++){
   final=await(await page.request.get('http://127.0.0.1:8088/coding/jobs/'+job.job_id)).json();
   if(final.state!=='running')break;
   await page.waitForTimeout(1000);
  }
  fs.writeFileSync(path.join(out,'ide-run-result.json'),JSON.stringify(final,null,2));
  await page.getByLabel('Coding task conversation').locator('.coding-turn-status').last().getByText('Completed',{exact:true}).waitFor();
  await page.screenshot({path:path.join(out,'ide-run.png')});
  console.log(JSON.stringify({state:final.state,answer:final.result?.answer,error:final.error}));
  if(final.state!=='completed'||!JSON.stringify(final).includes('http_response_success'))throw new Error('Existing project run did not verify HTTP readiness');
 } finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
