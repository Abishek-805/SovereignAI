const {chromium}=require('playwright');
const fs=require('node:fs');const path=require('node:path');
const out=path.resolve(__dirname,'../../../../outputs/full-qa-audit/ui');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:900}});const requests=[];
 page.on('request',r=>{if(r.method()==='POST')requests.push({url:r.url(),body:r.postData()})});
 try{
  await page.goto('http://127.0.0.1:8088/#/');
  const knowledge=page.getByRole('switch',{name:'Connect Knowledge'}).first();
  if(await knowledge.getAttribute('aria-checked')==='true')await knowledge.click();
  const chat=page.getByRole('textbox',{name:'Chat message'});
  await chat.fill('Explain bubble sort in three short sentences.');
  const completion=page.waitForResponse(r=>r.url().endsWith('/v1/chat/completions')&&r.request().method()==='POST',{timeout:120000});
  const start=Date.now();await page.getByRole('button',{name:'Send',exact:true}).click();
  const response=await completion;const stream=await response.text();
  const chunks=stream.split(/\r?\n/).filter(s=>s.startsWith('data: ')).flatMap(s=>{try{return [JSON.parse(s.slice(6))]}catch{return []}});
  const answer=chunks.map(c=>c.choices?.[0]?.delta?.content||'').join('');
  if(response.status()!==200||answer.length<30||chunks.length<2)throw new Error('Missing real streamed answer');
  await page.waitForFunction(()=>document.body.innerText.toLowerCase().includes('bubble sort'));
  if(requests.some(r=>/\/agent\/jobs|\/documents\/jobs|\/coding\//.test(r.url)))throw new Error('Normal chat entered unnecessary tool workflow');
  fs.writeFileSync(path.join(out,'normal-chat.json'),JSON.stringify({answer,stream_chunks:chunks.length,latency_ms:Date.now()-start,requests},null,2));
  await page.screenshot({path:path.join(out,'../screenshots/current-normal-chat.png')});
  console.log('Real browser chat streamed without Agent/RAG/Docker requests');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});

