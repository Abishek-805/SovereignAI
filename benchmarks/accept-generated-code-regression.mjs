// Actual model generation, isolated project, acceptance and host-file persistence.
import {chromium} from '../frontend/llama-ui/node_modules/playwright/index.mjs';
import {mkdir,writeFile} from 'node:fs/promises';
const base='http://127.0.0.1:8088',out='benchmarks/accept-generated-code-regression';
await mkdir(out,{recursive:true});
async function api(path,body,method=body?'POST':'GET'){
 const response=await fetch(base+path,{method,headers:{'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});
 const result=await response.json();if(!response.ok)throw Error(JSON.stringify(result));return result;
}
const workspace=await api('/coding/workspaces',{name:'Accept generated code regression '+Date.now()});
const id=workspace.workspace_id,name='accept_division.py',errors=[];
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
let result={passed:false,workspace_id:id};
try{
 const context=await browser.newContext({viewport:{width:1600,height:900},serviceWorkers:'block'});
 await context.addInitScript(id=>{localStorage.setItem('sovereign-active-workspace',id);localStorage.setItem('sovereign-code-auto-save','1');},id);
 const page=await context.newPage();page.on('pageerror',error=>errors.push(String(error)));
 await page.goto(base);await page.getByRole('navigation',{name:'Primary workbench navigation'}).getByRole('button',{name:'Code',exact:true}).click();
 await page.getByRole('combobox',{name:'Open coding workspace'}).selectOption(id);
 const prompt=page.locator('.assistant-composer textarea');await prompt.waitFor();
 await prompt.fill('Create '+name+' with divide(a,b) returning a/b and rejecting a zero divisor. Only create this new file.');await prompt.press('Enter');
 await page.locator('.source-diff .monaco-diff-editor').waitFor({timeout:180000});
 const before=await api(`/coding/workspaces/${id}/files/${name}`);
 if(!before.content.includes('def divide'))throw Error('Generated file missing');
 // Leave review open longer than autosave debounce. Hidden stale drafts must never write.
 await page.waitForTimeout(1800);
 if((await api(`/coding/workspaces/${id}/files/${name}`)).sha256!==before.sha256)throw Error('Review autosave changed generated file');
 await page.locator('.editor-actions').getByRole('button',{name:'Accept',exact:true}).click();
 await page.locator('.source-diff').waitFor({state:'detached'});await page.locator('.source-editor .monaco-editor').waitFor();
 await page.waitForFunction(()=> /def\s+divide/.test(document.querySelector('.source-editor .view-lines')?.textContent||''));
 await page.waitForTimeout(1800);await page.getByRole('button',{name:'Save',exact:true}).click();
 const after=await api(`/coding/workspaces/${id}/files/${name}`);
 if(after.sha256!==before.sha256)throw Error('Accept/save lost generated code');
 await page.reload();await page.getByRole('navigation',{name:'Primary workbench navigation'}).getByRole('button',{name:'Code',exact:true}).click();
 await page.locator(`.tree button[title="${name}"]`).click();
 await page.waitForFunction(()=> /def\s+divide/.test(document.querySelector('.source-editor .view-lines')?.textContent||''));
 if((await api(`/coding/workspaces/${id}/files/${name}`)).sha256!==before.sha256)throw Error('Reload lost persisted file');
 if(errors.filter(error=>!error.startsWith('Canceled: Canceled')).length)throw Error(errors.join('\n'));
 await page.screenshot({path:out+'/accepted-persisted-code.png'});
 result={passed:true,workspace_id:id,file:name,sha256:before.sha256,checks:['actual generation','review autosave isolation','accept editor content','save hash unchanged','reload persistence'],errors};
 console.log(JSON.stringify(result));
}finally{await writeFile(out+'/results.json',JSON.stringify(result,null,2));await browser.close();}
