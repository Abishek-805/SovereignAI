// Production layout checks; no model job or fabricated task activity.
import {chromium} from '../frontend/llama-ui/node_modules/playwright/index.mjs';
import {mkdir,writeFile} from 'node:fs/promises';
const output='benchmarks/agent-layout-acceptance/';await mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true}),checks=[],errors=[];
try{for(const width of [1366,390]){for(const dark of [false,true]){
 const context=await browser.newContext({viewport:{width,height:844},serviceWorkers:'block',colorScheme:dark?'dark':'light'}),page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));await page.goto('http://127.0.0.1:8088');
 if(width<768)await page.getByRole('button',{name:'Expand navigation',exact:true}).click();await page.getByRole('navigation',{name:'Primary workbench navigation'}).getByRole('button',{name:'Agent',exact:true}).click();await page.getByLabel('Task request').waitFor();
 const bounds=await page.locator('.agent-chat').boundingBox(),composer=await page.locator('.agent-chat .composer').boundingBox();if(!bounds||bounds.y+bounds.height>845||!composer||composer.x<0||composer.x+composer.width>width||composer.y+composer.height>845)throw Error('Agent/composer viewport clipping '+width);
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth||document.documentElement.scrollHeight>innerHeight))throw Error('Outer Agent scroll '+width);
 await page.getByLabel('Task request').fill('Draft remains editable before submission');await page.getByLabel('Task request').press('Shift+Enter');if(!(await page.getByLabel('Task request').inputValue()).includes('\n'))throw Error('Shift Enter did not insert newline');
 await page.screenshot({path:output+`agent-${width}-${dark?'dark':'light'}.png`});checks.push({test:'Chat-like Agent empty state and editable composer',width,dark,passed:true});await context.close();
 }}if(errors.length)throw Error(errors.join('\n'));await writeFile(output+'results.json',JSON.stringify({checks,errors},null,2));console.log(JSON.stringify({checks,errors},null,2));}finally{await browser.close();}
