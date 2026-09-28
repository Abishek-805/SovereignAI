// Production layout regression only. Isolated browser contexts; no document/project writes or model calls.
import {chromium} from '../frontend/llama-ui/node_modules/playwright/index.mjs';
import {mkdir,writeFile} from 'node:fs/promises';
const base=process.env.SOVEREIGN_BASE||'http://127.0.0.1:8088',output='benchmarks/final-layout-acceptance/';
await mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const checks=[],errors=[],mutations=[];
const assert=(ok,message)=>{if(!ok)throw Error(message);};
try{
 for(const theme of ['dark','light'])for(const width of [1366,390]){
  const ctx=await browser.newContext({viewport:{width,height:844},serviceWorkers:'block'});
  await ctx.addInitScript(theme=>localStorage.setItem('mode-watcher-mode',theme),theme);
  const page=await ctx.newPage();page.on('pageerror',e=>errors.push(String(e)));
  page.on('request',r=>{const path=new URL(r.url()).pathname;if(r.method()!=='GET'&&/^\/(?:agent\/jobs|documents\/(?:jobs|import)|coding\/workspaces|(?:v1\/)?chat\/completions)/.test(path))mutations.push(r.method()+' '+path);});
  await page.goto(base);await page.locator('.sovereign-chat-form').waitFor();
  const nav=async(destination)=>{const back=page.getByRole('button',{name:'Go back',exact:true});if(await back.isVisible())await back.click();const expand=page.getByRole('button',{name:'Expand navigation',exact:true});if(width<768&&await expand.isVisible())await expand.click();await page.getByRole('navigation',{name:'Primary workbench navigation'}).getByRole('button',{name:destination,exact:true}).click();};
  await nav('Control Center');await page.getByRole('button',{name:'Appearance',exact:true}).click();await page.getByRole('button',{name:theme,exact:true}).click();
  for(const destination of ['Chat','Knowledge','Agent','Code','Control Center']){
   await nav(destination);
   // The destination navigation state and frame settle before measuring.
   if(destination==='Agent')await page.getByLabel('Task request').waitFor();else if(destination==='Knowledge')await page.getByLabel('Search documents').waitFor();else if(destination==='Code')await page.locator('.ide').waitFor();
   await page.waitForTimeout(300);
   const geometry=await page.evaluate(()=>({width:innerWidth,height:innerHeight,rootWidth:document.documentElement.scrollWidth,rootHeight:document.documentElement.scrollHeight,bodyWidth:document.body.scrollWidth,bodyHeight:document.body.scrollHeight}));
   assert(geometry.rootWidth<=width+1&&geometry.bodyWidth<=width+1,`${destination} ${theme} ${width} horizontal root overflow: ${JSON.stringify(geometry)}`);
   assert(geometry.rootHeight<=845&&geometry.bodyHeight<=845,`${destination} ${theme} ${width} vertical root overflow: ${JSON.stringify(geometry)}`);
   await page.screenshot({path:output+`${destination.toLowerCase().replace(' ','-')}-${theme}-${width}.png`});
   checks.push({test:`${destination} ${theme} ${width} fits viewport`,passed:true,geometry});
  }
  await ctx.close();
 }
 assert(!errors.length,errors.join('\n'));assert(!mutations.length,'Unexpected user data/model mutation: '+mutations.join(','));
 const result={scope:'Production baseline layout only; no user-data writes or inference',checks,pageErrors:errors,mutations};await writeFile(output+'results.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
}finally{await browser.close();}
