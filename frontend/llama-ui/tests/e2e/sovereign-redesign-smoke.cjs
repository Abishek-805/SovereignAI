const { chromium } = require('playwright');
const path = require('node:path');
(async () => {
 const browser = await chromium.launch({headless:true, executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try {
  const page = await browser.newPage({viewport:{width:1440,height:900}});
  const errors=[]; page.on('pageerror',error=>errors.push(error.message));
  await page.goto('http://127.0.0.1:8088/#/',{waitUntil:'domcontentloaded'});
  await page.getByRole('heading',{name:'What are we working on?'}).waitFor();
  await page.screenshot({path:path.join(process.env.TEMP,'sovereign-redesign-home.png')});
  const nav=page.getByRole('navigation',{name:'Primary workbench navigation'});
  await nav.getByRole('button',{name:'New task',exact:true}).click();
  await page.getByRole('button',{name:'Calculate',exact:true}).click();
  await page.getByLabel('Describe your task').fill('Calculate: (8.2 - 7.1) * 2');
  await page.getByRole('button',{name:/Start task/}).click();
  await page.getByText('Task details · completed',{exact:true}).waitFor({timeout:30000});
  if (!(await page.locator('#sovereign-documents').innerText()).includes('2.2')) throw Error('Missing calculation result');
  await page.screenshot({path:path.join(process.env.TEMP,'sovereign-redesign-task.png')});
  await nav.getByRole('button',{name:'Tools & models',exact:true}).click();
  await page.getByText('sovereign-text',{exact:true}).waitFor();
  await page.getByText('Verified Docker engine ready',{exact:true}).waitFor({timeout:15000});
  await nav.getByRole('button',{name:'Code workspace',exact:true}).click();
  await page.getByRole('region',{name:'Coding workspace',exact:true}).waitFor();
  await page.setViewportSize({width:390,height:844});
  const box=await page.locator('#sovereign-documents').boundingBox();
  if (!box || box.x < 0 || box.x+box.width>391) throw Error('Mobile overflow');
  await page.screenshot({path:path.join(process.env.TEMP,'sovereign-redesign-mobile.png')});
  await page.getByRole('button',{name:'Go back'}).click();
  await page.getByRole('heading',{name:'What are we working on?'}).waitFor();
  if(errors.length) throw Error(errors.join('\n'));
  console.log('PASS: home, navigation, real calculation, models, Docker readiness, code, mobile bounds, return to chat; no browser errors');
 } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
