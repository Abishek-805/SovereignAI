// Real Code assistant request on the suite-owned clone of Summa.
import {chromium} from '../frontend/llama-ui/node_modules/playwright/index.mjs';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
const fixture=JSON.parse(await readFile('benchmarks/mixed-project-agent-results.json','utf8'));
const base='http://127.0.0.1:8088',out='benchmarks/mixed-project-ide-acceptance/';await mkdir(out,{recursive:true});
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const context=await browser.newContext({viewport:{width:1920,height:990},serviceWorkers:'block'});
await context.addInitScript(id=>{localStorage.setItem('sovereign-active-workspace',id);localStorage.setItem('mode-watcher-mode','dark');},fixture.workspace_id);
const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));
let job;
try{
 await page.goto(base);
 await page.getByRole('navigation',{name:'Primary workbench navigation'}).getByRole('button',{name:'Code',exact:true}).click();
 await page.locator('.ide').waitFor();
 const name='ide_acceptance_'+Date.now()+'.py';
 const prompt=page.locator('.ai-panel textarea');await prompt.waitFor();
 await page.getByRole('combobox',{name:'Open coding workspace'}).selectOption(fixture.workspace_id);
 await page.locator('.tree button[title="division.py"]').waitFor();
 const started=page.waitForResponse(r=>r.url().endsWith('/agent/jobs')&&r.request().method()==='POST');
 await prompt.fill('Create '+name+' with a subtract(a,b) function returning a-b. Only create this new file.');await prompt.press('Enter');
 const response=await started;const admitted=await response.json();
 if(response.request().postDataJSON().workspace_id!==fixture.workspace_id)throw Error('Code assistant sent wrong project');
 for(let i=0;i<180;i++){job=await(await fetch(base+'/coding/jobs/'+admitted.job_id)).json();if(job.state!=='running')break;await new Promise(r=>setTimeout(r,1000));}
 if(job.state!=='completed'||job.result?.result?.state==='failed')throw Error(JSON.stringify(job));
 await page.locator(`.tree button[title="${name}"]`).waitFor({timeout:10000});
 await page.locator(`.tree button[title="${name}"]`).click();
 await page.waitForFunction(()=>/def\s+subtract/.test(document.querySelector('.source-editor .view-lines')?.textContent||''));
 if(await page.evaluate(()=>document.documentElement.scrollHeight>innerHeight+1))throw Error('Outer scrollbar returned');
 await page.screenshot({path:out+'created-file.png'});
 if(errors.filter(e=>!e.startsWith('Canceled: Canceled')).length)throw Error(errors.join('\n'));
 await writeFile(out+'results.json',JSON.stringify({passed:true,workspace_id:fixture.workspace_id,file:name,job,errors},null,2));
 console.log(JSON.stringify({passed:true,elapsed:job.elapsed,file:name}));
}finally{await browser.close();}
