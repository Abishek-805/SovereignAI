// Real production interactions. No fabricated model responses or project edits.
import { chromium } from '../frontend/llama-ui/node_modules/playwright/index.mjs';
import { mkdir, writeFile } from 'node:fs/promises';
const output='benchmarks/ui-acceptance/';
await mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const checks=[];
const ensure=(condition,message)=>{if(!condition)throw Error(message);};
try {
 for(const width of [1366,390]) {
  const context=await browser.newContext({viewport:{width,height:844},serviceWorkers:'block'});
  const page=await context.newPage();
  await page.goto('http://127.0.0.1:8088',{waitUntil:'domcontentloaded'});
  const nav=async name=>{if(width<768){if(await page.getByRole('button',{name:'Go back',exact:true}).isVisible())await page.getByRole('button',{name:'Go back',exact:true}).click();await page.getByRole('button',{name:'Expand navigation',exact:true}).click();}await page.getByRole('button',{name,exact:true}).click();};
  await page.locator('.sovereign-chat-form').waitFor();await page.screenshot({path:output+`chat-${width}.png`});
  await page.getByLabel('Model and routing',{exact:true}).click();
  await page.locator('.routing-popover .model-row').first().waitFor();
  const modelBounds=await page.getByRole('dialog',{name:'Model and routing details'}).boundingBox();
  ensure(modelBounds.x>=0&&modelBounds.x+modelBounds.width<=width+1,'Model details overflow horizontally');
  await page.screenshot({path:output+`routing-${width}.png`});
  await page.keyboard.press('Escape');
  ensure(await page.getByRole('dialog',{name:'Model and routing details'}).count()===0,'Model details did not close on Escape');
  checks.push({surface:'model-control',width,viewportFit:true,escape:true});
  await nav('Code');
  await page.locator('.ide').waitFor();
  await page.locator('.ide').evaluate(el=>Promise.allSettled(el.getAnimations().map(animation=>animation.finished)));
  const codeBounds=await page.locator('.ide').boundingBox();
  ensure(codeBounds.y+codeBounds.height<=845,'Code extends beyond the viewport');
  if(width===390){
   ensure(await page.locator('.explorer').count()===0,'Mobile Explorer did not collapse');
   await page.getByRole('button',{name:'Toggle Assistant',exact:true}).click();
   const composer=await page.locator('.assistant-composer').boundingBox();
   ensure(composer.y+composer.height<=844,'Mobile assistant composer is clipped');
   await page.screenshot({path:output+'code-mobile-assistant.png'});
   await page.getByRole('button',{name:'Toggle Assistant',exact:true}).click();
  }
  await page.screenshot({path:output+`code-${width}.png`});
  checks.push({surface:'code',width,viewportFit:true});
  await nav('Control Center');
  for(const section of ['Models & routing','Runtimes','System & downloads','Appearance']){
   await page.getByRole('button',{name:section,exact:true}).click();
   await page.screenshot({path:output+`control-${section.split(' ')[0]}-${width}.png`});
  }
  await page.getByRole('button',{name:'Documents & evidence',exact:true}).click();
  ensure(await page.locator('.control-body h4').count()===1,'Duplicate document heading in Control Center');
  await page.getByRole('button',{name:'Open document workspace',exact:true}).click();
  await page.getByLabel('Search documents',{exact:true}).fill('24ALR001');
  ensure(await page.locator('.knowledge-files button').count()===1,'Library search failed');
  await page.locator('.knowledge-files button').first().click();
  await page.getByRole('button',{name:'Rename',exact:true}).click();
  const dialog=page.getByRole('dialog');await dialog.waitFor();
  await dialog.getByRole('button',{name:'Cancel',exact:true}).focus();await page.keyboard.press('Tab');
  ensure(await page.evaluate(()=>!!document.activeElement.closest('[role=dialog]')),'Dialog focus escaped');
  await page.keyboard.press('Escape');await dialog.waitFor({state:'detached'});
  ensure(await page.locator('.knowledge-library').isVisible(),'Dialog Escape closed Knowledge');
  checks.push({surface:'document-library',width,search:true,focusContained:true,escape:true});
  await context.close();
 }
 const context=await browser.newContext({viewport:{width:1366,height:768},serviceWorkers:'block'});
 const page=await context.newPage();
 await page.goto('http://127.0.0.1:8088',{waitUntil:'domcontentloaded'});
 await page.getByLabel('Agent',{exact:true}).click();
 await page.getByRole('button',{name:'New chat',exact:true}).click();
 await page.getByRole('button',{name:'Project context',exact:true}).click();
 await page.locator('.project-options').getByRole('button',{name:'Summa',exact:true}).click();
 const responsePromise=page.waitForResponse(r=>r.url().endsWith('/agent/jobs')&&r.request().method()==='POST');
 const prompt=page.locator('.agent-chat textarea');
 await prompt.fill('What is your name?');await prompt.press('Enter');
 await page.locator('.user-message').filter({hasText:'What is your name?'}).waitFor();
 await page.locator('.agent-chat').getByRole('button',{name:'Stop',exact:true}).waitFor();
 await page.screenshot({path:output+'agent-pending-identity.png'});
 const job=await (await responsePromise).json();
 await page.locator('.assistant-message p').filter({hasText:/Sovereign/i}).waitFor({timeout:120000});
 const result=await (await page.request.get('http://127.0.0.1:8088/coding/jobs/'+job.job_id)).json();
 ensure(result.result.plan.action==='answer','Identity request selected a tool');
 ensure(!result.events.some(e=>/project structure|editing|Docker/i.test(e.stage)),'Identity request inspected a project');
 checks.push({surface:'agent',test:'real identity with selected project',action:result.result.plan.action,answer:result.result.answer,events:result.events});
 await page.getByRole('button',{name:'New chat',exact:true}).click();
 ensure(await page.locator('.user-message').count()===0,'New chat did not clear transcript');
 await page.getByRole('button',{name:/^History/}).click();
 await page.locator('.agent-history-row').getByRole('button',{name:/^What is your name/}).click();
 await page.locator('.user-message').filter({hasText:'What is your name?'}).waitFor();
 checks.push({surface:'agent',test:'New chat and history restore',passed:true});
 await page.screenshot({path:output+'agent-completed-identity.png'});
 await prompt.fill('Explain the advantages and disadvantages of binary search trees in detail.');
 const stopJobResponse=page.waitForResponse(r=>r.url().endsWith('/agent/jobs')&&r.request().method()==='POST');
 await prompt.press('Enter');
 await page.locator('.agent-chat').getByRole('button',{name:'Stop',exact:true}).click();
 const stoppedJob=await (await stopJobResponse).json();
 await page.locator('.assistant-message p').filter({hasText:'Task stopped.'}).waitFor({timeout:120000});
 const cancelled=await (await page.request.get('http://127.0.0.1:8088/coding/jobs/'+stoppedJob.job_id)).json();
 ensure(cancelled.state==='cancelled','Stop did not cancel the backend job');
 checks.push({surface:'agent',test:'Stop cancels actual inference job',state:cancelled.state});
 await page.getByRole('navigation',{name:'Primary workbench navigation'}).getByRole('button',{name:'Code',exact:true}).click();await page.locator('.ide').waitFor();
 await page.locator('.new-coding-chat').click();const codingInput=page.getByLabel('Coding task',{exact:true});const codeChecks=[];
 for(const question of ['hi','How are you?','whats up?','What is your name?','What is a prime number?','Thanks!']){
  const response=page.waitForResponse(r=>r.url().endsWith('/agent/jobs')&&r.request().method()==='POST');await codingInput.fill(question);await codingInput.press('Enter');const admitted=await response;ensure(admitted.status()===200,'Code conversational request rejected: '+admitted.status());const payload=admitted.request().postDataJSON();ensure(payload.history.length<=8,'Code history exceeds API contract');const job=await admitted.json();await page.locator('.assistant-composer button.primary').filter({hasText:'Send'}).waitFor({timeout:120000});const state=await(await page.request.get('http://127.0.0.1:8088/coding/jobs/'+job.job_id)).json();ensure(state.state==='completed'&&state.result.plan.action==='answer','Code conversation incorrectly executed project work: '+JSON.stringify(state));ensure(!state.events.some(e=>/Reading project|Editing|Docker/.test(e.stage)),'Code conversation read project');codeChecks.push({question,historyEntries:payload.history.length,answer:state.result.answer});
 }
 ensure(await page.locator('.coding-answer').count()===6,'Code did not retain all real conversational answers');await page.screenshot({path:output+'code-conversation-history.png'});checks.push({surface:'code',test:'Six real model conversations stay within history contract without file work',turns:codeChecks});
 // Connected Chat citations and Agent Word export are exercised in knowledge-context-acceptance.mjs.
 await context.close();
}finally{
 await writeFile(output+'integration-results.json',JSON.stringify(checks,null,2));
 await browser.close();
 console.log(JSON.stringify(checks,null,2));
}
