// Frontend asset-cache smoke check; this is not the OS-enforced offline gate.
import { chromium } from '../frontend/llama-ui/node_modules/playwright/index.mjs';
import { writeFile } from 'node:fs/promises';
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try {
 const context=await browser.newContext({viewport:{width:1366,height:768},serviceWorkers:'allow'});
 const page=await context.newPage();
 const errors=[],warnings=[];
 page.on('console',message=>{if(message.type()==='error')errors.push(message.text());if(message.type()==='warning')warnings.push(message.text());});
 await page.goto('http://127.0.0.1:8088',{waitUntil:'domcontentloaded'});
 await page.locator('.sovereign-chat-form').waitFor();
 try {
  await page.waitForFunction(async()=>{const registration=await navigator.serviceWorker.getRegistration();return registration?.active?.state==='activated';},undefined,{timeout:60000});
 }catch(error){console.log(JSON.stringify({errors,registrations:await page.evaluate(async()=>Promise.all((await navigator.serviceWorker.getRegistrations()).map(r=>({scope:r.scope,active:r.active?.state,installing:r.installing?.state,waiting:r.waiting?.state}))))},null,2));throw error;}
 // The first installation controls subsequent navigations, not necessarily its installer page.
 await page.reload({waitUntil:'domcontentloaded'});
 await page.evaluate(()=>navigator.serviceWorker.ready.then(()=>true));
 await page.reload({waitUntil:'domcontentloaded'});
 await page.waitForFunction(()=>!!navigator.serviceWorker.controller).catch(async error=>{console.log(JSON.stringify({errors,state:await page.evaluate(async()=>({controller:navigator.serviceWorker.controller?.scriptURL,registrations:(await navigator.serviceWorker.getRegistrations()).map(r=>({scope:r.scope,active:r.active?.state,waiting:r.waiting?.state,installing:r.installing?.state}))}))},null,2));throw error;});
 const cache=await page.evaluate(async()=>({controller:navigator.serviceWorker.controller.scriptURL,caches:await caches.keys()}));
 await context.setOffline(true);
 await page.reload({waitUntil:'domcontentloaded'});
 await page.locator('.sovereign-chat-form').waitFor();
 await page.getByRole('button',{name:'Code',exact:true}).click();
 await page.locator('.ide').waitFor();
 await page.screenshot({path:'benchmarks/ui-acceptance/pwa-offline-shell.png'});
 const result={test:'Cached split frontend starts with browser networking disabled',passed:true,scope:'Frontend shell only. No inference or OS network isolation claim.',...cache,preloadWarnings:[...new Set(warnings.filter(message=>/preload|cross-world/i.test(message)))]};
 await writeFile('benchmarks/ui-acceptance/pwa-results.json',JSON.stringify(result,null,2));
 console.log(JSON.stringify(result,null,2));
 await context.close();
}finally{await browser.close();}
