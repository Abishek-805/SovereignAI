const {chromium}=require('playwright');const fs=require('node:fs');const path=require('node:path');
const out=path.resolve(process.env.SOVEREIGN_QA_OUTPUT||path.resolve(__dirname,'../../../../outputs/product-verification-20261004'));fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:900}});
 try{
  const name='browser-source-'+Date.now()+'.txt';
  await page.goto('http://127.0.0.1:8088/#/');
  await page.getByRole('navigation',{name:'Primary workbench navigation'}).getByRole('button',{name:'Control Center',exact:true}).click();
  await page.getByRole('navigation',{name:'Control Center sections'}).getByRole('button',{name:'Documents & evidence',exact:true}).click();
  await page.getByRole('button',{name:'Open document workspace',exact:true}).click();
  const library=page.getByRole('region',{name:'Knowledge library'});
  await library.locator('input[type=file]').first().setInputFiles({name,mimeType:'text/plain',buffer:Buffer.from('The browser verification facility has exactly 7 repair bays. Its supervisor is Mira.\n')});
  await library.getByText(name,{exact:true}).first().waitFor({timeout:90000});
  await library.getByText(/7 repair bays/).first().waitFor({timeout:90000});
  await page.getByRole('button',{name:'Go back',exact:true}).click();
  await page.getByRole('button',{name:'Go back',exact:true}).click();
  const knowledge=page.getByRole('switch',{name:'Connect Knowledge'}).first();
  if(await knowledge.getAttribute('aria-checked')!=='true')await knowledge.click();
  await page.getByRole('button',{name:/All documents|\d+ selected/}).first().click();
  const dialog=page.getByRole('dialog',{name:'Connect Knowledge'});
  await dialog.getByRole('checkbox',{name:/All documents in Knowledge/}).uncheck();
  await dialog.getByRole('textbox',{name:'Search Knowledge'}).fill(name);
  await dialog.getByRole('checkbox',{name:new RegExp(name)}).check();
  await dialog.getByRole('button',{name:'Connect',exact:true}).click();
  await page.getByRole('textbox',{name:'Chat message'}).fill('How many repair bays does the facility have and who supervises it? Cite the source.');
  const completion=page.waitForResponse(r=>r.url().endsWith('/documents/jobs')&&r.request().method()==='POST',{timeout:60000});
  await page.getByRole('button',{name:'Send',exact:true}).click();
  const response=await completion;const admitted=await response.json();let final;
  for(let n=0;n<180;n++){
   final=await(await page.request.get('http://127.0.0.1:8088/coding/jobs/'+admitted.job_id)).json();
   if(final.state!=='running')break;
   await page.waitForTimeout(1000);
  }
  const answer=final.result?.answer||'';
  if(final.state!=='completed'||!answer.includes('7')||!answer.includes('Mira')||!/\[S\d+\]/.test(answer)||!final.result.sources.length)throw new Error('Grounded browser answer missing: '+JSON.stringify(final));
  const submitted=JSON.parse(response.request().postData());
  if(submitted.document_ids?.length!==1||final.result.sources.some(s=>s.document_id!==submitted.document_ids[0]))throw new Error('Citation source differs from selected document');
  await page.waitForFunction(()=>document.body.innerText.includes('Mira'));
  fs.writeFileSync(path.join(out,'browser-rag.json'),JSON.stringify({source:name,request:JSON.parse(response.request().postData()),answer,job:final,grounded:true},null,2));
  await page.screenshot({path:path.join(out,'browser-rag.png')});
  console.log('Browser upload, source selection, real model grounded answer and citation passed');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
