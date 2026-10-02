// Browser-rendered geometry/style oracle; candidate cannot redefine the checker.
import { createRequire } from 'node:module';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
const root=path.dirname(fileURLToPath(import.meta.url));
const require=createRequire(path.join(root,'../../frontend/llama-ui/package.json'));
const {chromium}=require('playwright');
const [mode, fixture, candidate]=process.argv.slice(2);
const browser=await chromium.launch({headless:true});
try {
 const page=await browser.newPage({viewport:{width:960,height:600},deviceScaleFactor:1});
 await page.goto(pathToFileURL(mode==='render'?path.join(root,fixture,'reference.html'):path.resolve(candidate)).href);
 const metrics=await page.evaluate(()=>({text:document.body.innerText,labels:[...document.querySelectorAll('label')].map(e=>[e.htmlFor,!!document.getElementById(e.htmlFor)]),items:[...document.querySelectorAll('[id]')].map(e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return {id:e.id,tag:e.tagName,x:r.x,y:r.y,width:r.width,height:r.height,background:s.backgroundColor,color:s.color,borderRadius:s.borderRadius};})}));
 if(mode==='render') {
  await page.screenshot({path:path.join(root,fixture,'target.png')});
  await writeFile(path.join(root,fixture,'reference-metrics.json'),JSON.stringify(metrics,null,2)+'\n');
  console.log(JSON.stringify({fixture,rendered:true,browser:browser.version()}));
 } else {
  const expected=JSON.parse(await readFile(path.join(root,fixture,'reference-metrics.json'),'utf8'));
  const failures=[];
  if(metrics.text!==expected.text)failures.push('visible content changed');
  if(JSON.stringify(metrics.labels)!==JSON.stringify(expected.labels))failures.push('label associations changed');
  for(const target of expected.items){const actual=metrics.items.find(e=>e.id===target.id);if(!actual){failures.push('missing '+target.id);continue;}if(actual.tag!==target.tag)failures.push(target.id+' tag');for(const k of ['x','y','width','height'])if(Math.abs(actual[k]-target[k])>4)failures.push(target.id+' '+k);for(const k of ['background','color','borderRadius'])if(actual[k]!==target[k])failures.push(target.id+' '+k);}
  console.log(JSON.stringify({fixture,passed:failures.length===0,failures}));
  process.exitCode=failures.length?1:0;
 }
} finally {await browser.close();}
