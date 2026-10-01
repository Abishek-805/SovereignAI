const {chromium}=require('../frontend/llama-ui/node_modules/playwright');
// Uses an isolated browser profile and mocked generation; never changes real conversations.
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1920,height:990},serviceWorkers:'block'});
 let polls=0;const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.route('**/documents/jobs',route=>route.fulfill({json:{job_id:'scroll-fixture'}}));
 await page.route('**/coding/jobs/scroll-fixture',route=>{
  polls++;
  return route.fulfill({json:polls<5?{state:'running',stage:'Planning fixture '+polls}:{state:'completed',result:{status:'answered',answer:Array.from({length:35},(_,i)=>`Paragraph ${i+1}: verified scroll fixture content.`).join('\n\n')}}});
 });
 try{
  await page.goto((process.env.SOVEREIGN_TEST_URL || 'http://127.0.0.1:8088/')+'#/');
  const input=page.getByRole('textbox',{name:'Chat message'});await input.waitFor();
  await input.fill('Scroll regression fixture');await page.getByRole('button',{name:'Send',exact:true}).click();
  await page.getByText('Planning fixture 2',{exact:true}).waitFor();
  await page.getByText('Paragraph 35: verified scroll fixture content.',{exact:true}).waitFor();
  await page.waitForTimeout(600);
  const geometry=await page.evaluate(()=>{
    const last=document.querySelector('.chat-message:last-child .chat-message-assistant');
    const controls=document.querySelector('.chat-screen-form-wrapper');
    const rect=last.getBoundingClientRect(),composer=controls.getBoundingClientRect();
    return {scrollTop:document.documentElement.scrollTop,distance:document.documentElement.scrollHeight-innerHeight-document.documentElement.scrollTop,lastBottom:rect.bottom,composerTop:composer.top};
  });
  if(geometry.distance>5 || geometry.lastBottom>geometry.composerTop-8)throw Error('Current answer not followed or overlaps composer '+JSON.stringify(geometry));
  await page.mouse.wheel(0,-600);await page.waitForTimeout(400);
  const scrolled=await page.evaluate(()=>document.documentElement.scrollTop);
  await page.evaluate(()=>{document.querySelector('.chat-message:last-child .chat-message-assistant').append(document.createTextNode(' Layout update while reading history'));});
  await page.waitForTimeout(400);
  if(await page.evaluate(()=>document.documentElement.scrollTop)>scrolled+5)throw Error('Manual history scroll was overridden');
  const conversationUrl=page.url();
  const openings=[];
  for(let i=0;i<3;i++){
   await page.goto((process.env.SOVEREIGN_TEST_URL || 'http://127.0.0.1:8088/')+'#/');await input.waitFor();
   await page.goto(conversationUrl);await page.getByText('Paragraph 35: verified scroll fixture content.',{exact:true}).waitFor();
   await page.waitForTimeout(1200);
   if(i===1){await page.reload();await page.getByText('Paragraph 35: verified scroll fixture content.',{exact:true}).waitFor();await page.waitForTimeout(1200);}
   const opened=await page.evaluate(()=>({distance:document.documentElement.scrollHeight-innerHeight-document.documentElement.scrollTop,top:document.querySelector('.chat-screen-form-wrapper').getBoundingClientRect().top,bottom:document.querySelector('.chat-screen-form-wrapper').getBoundingClientRect().bottom}));
   openings.push(opened);
   if(opened.distance>5||Math.abs(opened.bottom-974)>5)throw Error('Inconsistent opening '+JSON.stringify(opened));
  }
  console.log(JSON.stringify({openings}));
  if(errors.length)throw Error(errors.join('\n'));


  console.log(JSON.stringify({geometry,manualScrollPreserved:true}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
