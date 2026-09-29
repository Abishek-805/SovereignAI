const { chromium } = require('playwright');

(async () => {
 const browser = await chromium.launch({headless:true, executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page = await browser.newPage({viewport:{width:1920,height:1080},colorScheme:'dark'});
 try {
  await page.goto('http://127.0.0.1:8088/#/');
  const heading=page.getByRole('heading',{name:'Ask anything. Start here.'});
  await heading.waitFor({timeout:20000});
  const welcome=await heading.boundingBox();
  const composer=await page.locator('.chat-screen-form-wrapper').boundingBox();
  if (!welcome || !composer || welcome.y<95 || composer.y<=welcome.y+welcome.height || composer.y>780)
   throw Error('New chat welcome and composer are clipped or separated incorrectly: '+JSON.stringify({welcome,composer}));
  if (await page.evaluate(()=>document.documentElement.scrollTop)>5)
   throw Error('New chat retained the previous conversation scroll position');
  console.log('New chat layout verified',JSON.stringify({welcome,composer}));
 } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1});
