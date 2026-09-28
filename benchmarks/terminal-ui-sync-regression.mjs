import {chromium} from '../frontend/llama-ui/node_modules/playwright/index.mjs';
import {mkdir,writeFile} from 'node:fs/promises';
const base='http://127.0.0.1:8088',out='benchmarks/terminal-ui-sync-regression';await mkdir(out,{recursive:true});
const workspace=await(await fetch(base+'/coding/workspaces',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'Terminal UI sync '+Date.now()})})).json();
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
let result={passed:false,workspace_id:workspace.workspace_id};
try{
 const context=await browser.newContext({viewport:{width:1600,height:900},serviceWorkers:'block'});
 const page=await context.newPage();await page.goto(base);
 await page.getByRole('navigation',{name:'Primary workbench navigation'}).getByRole('button',{name:'Code',exact:true}).click();
 await page.getByRole('combobox',{name:'Open coding workspace'}).selectOption(workspace.workspace_id);
 const terminal=page.getByRole('textbox',{name:'Terminal input',exact:true});
 async function command(text){await terminal.fill(text);await terminal.press('Enter');await page.locator('.console-tabs .running').waitFor();await page.locator('.console-tabs .running').waitFor({state:'detached',timeout:60000});}
 await command("printf 'first value\\n' > terminal_notes.txt");
 const item=page.locator('.tree button[title="terminal_notes.txt"]');await item.waitFor();await item.click();
 await page.waitForFunction(()=>/first\s+value/.test(document.querySelector('.source-editor .view-lines')?.textContent||''));
 await command("printf 'second value\\n' > terminal_notes.txt");
 await page.waitForFunction(()=>/second\s+value/.test(document.querySelector('.source-editor .view-lines')?.textContent||''));
 await command('rm terminal_notes.txt');await item.waitFor({state:'detached'});
 const actual=await(await fetch(base+'/coding/workspaces/'+workspace.workspace_id)).json();if(actual.files.length)throw Error('Deleted file remains in project');
 await page.screenshot({path:out+'/terminal-synced.png'});result={passed:true,workspace_id:workspace.workspace_id,checks:['created file appears in tree','edited file appears in open editor','deleted file leaves tree and host']};
 console.log(JSON.stringify(result));
}finally{await writeFile(out+'/results.json',JSON.stringify(result,null,2));await browser.close();}
