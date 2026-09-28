// Layout-only regression: long background Chat transcript must not leave an outer
// scrollbar behind fixed Workbench pages. No model calls or user data writes.
import {chromium} from '../frontend/llama-ui/node_modules/playwright/index.mjs';
import {mkdir,writeFile} from 'node:fs/promises';
const base='http://127.0.0.1:8088',out='benchmarks/workbench-scroll-acceptance/';await mkdir(out,{recursive:true});
const checks=[],errors=[];const ensure=(ok,message)=>{if(!ok)throw Error(message)};
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try{for(const [width,height] of [[1920,990],[1366,768],[390,844]]){
 const context=await browser.newContext({viewport:{width,height},serviceWorkers:'block'}),page=await context.newPage();page.on('pageerror',error=>errors.push(String(error)));
 await page.goto(base);await page.locator('.sovereign-chat-form').waitFor();
 await page.evaluate(()=>{const spacer=document.createElement('div');spacer.id='scroll-regression-transcript';spacer.style.height='5000px';spacer.textContent='Layout-only long conversation fixture';document.querySelector('.chat-screen').append(spacer);});
 ensure(await page.evaluate(()=>document.documentElement.scrollHeight>innerHeight+4000),'Long Chat fixture did not expose page scrolling');
 const navigate=async(destination)=>{const back=page.getByRole('button',{name:'Go back',exact:true});if(await back.isVisible())await back.click();const expand=page.getByRole('button',{name:'Expand navigation',exact:true});if(width<768&&await expand.isVisible())await expand.click();await page.getByRole('navigation',{name:'Primary workbench navigation'}).getByRole('button',{name:destination,exact:true}).click();};
 for(const destination of ['Code','Agent','Knowledge','Control Center']){
  await navigate(destination);await page.locator('.workbench-canvas:not(.canvas-hidden)').waitFor();await page.waitForTimeout(150);
  const geometry=await page.evaluate(()=>({rootHeight:document.documentElement.scrollHeight,rootWidth:document.documentElement.scrollWidth,height:innerHeight,width:innerWidth,backgroundOverflow:getComputedStyle(document.querySelector('.app-route-content')).overflow,bodyOverflow:getComputedStyle(document.body).overflow}));
  ensure(geometry.rootHeight<=height+1,`${destination} ${width}: outer vertical overflow ${JSON.stringify(geometry)}`);ensure(geometry.rootWidth<=width+1,`${destination} ${width}: horizontal overflow`);ensure(geometry.bodyOverflow!=='hidden','Blanket body scroll hide is not allowed');
  checks.push({test:`${destination} ${width} contains background transcript height`,passed:true,geometry});
  if(destination==='Code')ensure(await page.locator('.terminal-surface').evaluate(element=>['auto','scroll'].includes(getComputedStyle(element).overflowY)),'Terminal scroll is not preserved');
  if(destination==='Knowledge')ensure(await page.locator('.knowledge-files').evaluate(element=>['auto','scroll'].includes(getComputedStyle(element).overflowY)),'Library scroll is not preserved');
 }
 await navigate('Chat');
 ensure(await page.evaluate(()=>document.documentElement.scrollHeight>innerHeight+4000),'Returning to Chat lost transcript page scroll');checks.push({test:`Chat ${width} restores normal transcript scrolling`,passed:true});
 await page.screenshot({path:out+`chat-restored-${width}.png`});await context.close();
}ensure(!errors.length,errors.join('\n'));}finally{await writeFile(out+'results.json',JSON.stringify({checks,errors},null,2));await browser.close();console.log(JSON.stringify({checks,errors},null,2));}
