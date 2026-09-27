// Initial unavailable presentation is simulated; launch endpoint and subsequent readiness are real.
const { chromium } = require('playwright');
(async () => {
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  let first=true;
  await page.route('**/workbench/info',async route=>{
   if(!first) return route.continue();
   first=false;
   const response=await route.fetch(); const info=await response.json();
   info.sandbox.ready=false; info.sandbox.reason='Docker is stopped';
   await route.fulfill({response,json:info});
  });
  await page.goto('http://127.0.0.1:8088/#/',{waitUntil:'domcontentloaded'});
  await page.getByRole('navigation',{name:'Primary workbench navigation'}).getByRole('button',{name:'Tools & models'}).click();
  const started=page.waitForResponse(response=>response.url().endsWith('/workbench/docker/start'));
  await page.getByRole('button',{name:'Start Docker',exact:true}).click();
  if((await started).status()!==200) throw Error('Docker start endpoint failed');
  await page.getByText('Verified Docker engine ready',{exact:true}).waitFor({timeout:30000});
  console.log('PASS: Start Docker button calls real endpoint and refreshes actual sandbox readiness (initial unavailable state simulated).');
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
