// Production-only observations, not latency percentiles or a model benchmark.
import { chromium } from '../frontend/llama-ui/node_modules/playwright/index.mjs';
import { mkdir, writeFile } from 'node:fs/promises';
const label=process.argv[2]||'current';
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const runs=[];
try {
 for(let i=0;i<3;i++) {
  const context=await browser.newContext({viewport:{width:1366,height:768},serviceWorkers:'block'});
  const page=await context.newPage();
  await page.addInitScript(()=>{window.workbenchLongTasks=[];new PerformanceObserver(list=>window.workbenchLongTasks.push(...list.getEntries().map(e=>({start:e.startTime,duration:e.duration})))).observe({type:'longtask',buffered:true});});
  const started=Date.now();
  await page.goto('http://127.0.0.1:8088',{waitUntil:'domcontentloaded'});
  await page.getByRole('button',{name:'Control Center',exact:true}).waitFor();
  runs.push(await page.evaluate(elapsed=>({readyMs:elapsed,heapUsedBytes:performance.memory?.usedJSHeapSize??null,scriptTransferBytes:performance.getEntriesByType('resource').filter(e=>e.initiatorType==='script'||e.name.endsWith('.js')).reduce((n,e)=>n+e.transferSize,0),scriptDecodedBytes:performance.getEntriesByType('resource').filter(e=>e.initiatorType==='script'||e.name.endsWith('.js')).reduce((n,e)=>n+e.decodedBodySize,0),longTasks:window.workbenchLongTasks}),Date.now()-started));
  await context.close();
 }
}finally{await browser.close();}
await mkdir('benchmarks/ui-acceptance',{recursive:true});
await writeFile(`benchmarks/ui-acceptance/profile-${label}.json`,JSON.stringify({label,date:new Date().toISOString(),viewport:'1366x768',runs},null,2));
console.log(JSON.stringify({label,runs},null,2));
