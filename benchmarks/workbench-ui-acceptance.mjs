// Real browser acceptance against the running production workbench.
import { chromium } from '../frontend/llama-ui/node_modules/playwright/index.mjs';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const output = fileURLToPath(new URL('./ui-acceptance/', import.meta.url));
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true });
const checks = [];
try {
 for (const [width, height] of [[1920,1080],[1600,900],[1366,768],[800,700],[390,844]]) {
  const context = await browser.newContext({viewport:{width,height},serviceWorkers:'block'});
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:8088', {waitUntil:'domcontentloaded'});
  if(width<768)await page.getByRole('button',{name:'Expand navigation',exact:true}).click();
  await page.getByRole('button',{name:'Control Center',exact:true}).click();
  await page.getByRole('button',{name:'Documents & evidence',exact:true}).click();
  await page.getByRole('button',{name:'Open document workspace',exact:true}).click();
  for (const dark of [false,true]) {
   await page.reload({waitUntil:'domcontentloaded'});
   if(width<768)await page.getByRole('button',{name:'Expand navigation',exact:true}).click();
   await page.getByRole('button',{name:'Control Center',exact:true}).click();
   await page.getByRole('button',{name:'Appearance',exact:true}).click();
   await page.getByRole('button',{name:dark?'dark':'light',exact:true}).click();
   await page.waitForFunction(expected=>document.documentElement.classList.contains('dark')===expected,dark);
   await page.getByRole('button',{name:'Documents & evidence',exact:true}).click();
   await page.getByRole('button',{name:'Open document workspace',exact:true}).click();
   const dimensions = await page.evaluate(() => {
    const library=document.querySelector('.knowledge-library').getBoundingClientRect();
    return {rootHeight:document.documentElement.scrollHeight,viewport:innerHeight,horizontal:document.documentElement.scrollWidth>innerWidth,libraryBottom:library.bottom,
     scrollers:[...document.querySelectorAll('.workbench-content *')].filter(e=>e.getClientRects().length && e.scrollHeight>e.clientHeight+2 && ['auto','scroll'].includes(getComputedStyle(e).overflowY)).map(e=>e.className)};
   });
   if(dimensions.horizontal || dimensions.libraryBottom>height+1 || dimensions.rootHeight>height+1) throw new Error('Document viewport overflow '+JSON.stringify({width,height,...dimensions}));
   checks.push({page:'documents',width,height,dark,...dimensions});
   await page.screenshot({path:output+`documents-${width}-${dark?'dark':'light'}.png`});
  }
  await page.locator('.knowledge-files button').first().click();
  await page.screenshot({path:output+`library-${width}.png`});
  await page.getByRole('button',{name:'Go back',exact:true}).click();
  if(width<768){while(await page.getByRole('button',{name:'Go back',exact:true}).isVisible())await page.getByRole('button',{name:'Go back',exact:true}).click();await page.getByRole('button',{name:'Expand navigation',exact:true}).click();}
  await page.getByRole('navigation',{name:'Primary workbench navigation'}).getByRole('button',{name:'Agent',exact:true}).click();
  await page.getByRole('button',{name:'New chat',exact:true}).last().click();
  const agentBounds=await page.locator('.agent-chat').boundingBox();
  if(!agentBounds||agentBounds.y+agentBounds.height>height+1)throw new Error('Agent clipped at '+width);
  await page.screenshot({path:output+`agent-${width}.png`});
  checks.push({page:'agent',width,height,bounds:agentBounds});
  await context.close();
 }
 // Use the user's existing program, rather than creating a synthetic project.
 const context=await browser.newContext({viewport:{width:1600,height:900},serviceWorkers:'block'});
 const page=await context.newPage();
 await page.goto('http://127.0.0.1:8088',{waitUntil:'domcontentloaded'});
 await page.getByRole('button',{name:'Code',exact:true}).click();
 await page.getByLabel('Open coding workspace').selectOption('f2ac2ecf555048b6964e64eded90fc2e');
 await page.locator('.explorer-tree-area button[title="addition_operation.py"]').click();
 await page.locator('.run-action').click();
 await page.locator('.terminal-surface pre').filter({hasText:'Enter the first number'}).waitFor({timeout:60000});
 const input=page.getByLabel('Terminal input',{exact:true});
 await input.fill('3');await input.press('Enter');
 await page.locator('.terminal-surface pre').filter({hasText:'Enter the second number'}).waitFor({timeout:15000});
 await input.fill('5');await input.press('Enter');
 await page.locator('.terminal-surface pre').filter({hasText:'The sum of 3.0 and 5.0 is 8.0'}).waitFor({timeout:15000});
 checks.push({page:'code',test:'Direct terminal typing and Enter input',passed:true});
 await page.screenshot({path:output+'terminal-program.png'});
 await page.waitForFunction(()=>!document.querySelector('.run-action').disabled);
 await input.fill('pwd');await input.press('Enter');
 await page.locator('.terminal-surface pre').filter({hasText:'/output/project'}).waitFor({timeout:30000});
 checks.push({page:'code',test:'Docker shell command',passed:true});
 await page.screenshot({path:output+'terminal-command.png'});
 await context.close();
} finally {
 await writeFile(output+'results.json',JSON.stringify(checks,null,2));
 await browser.close();
 console.log(JSON.stringify(checks,null,2));
}
