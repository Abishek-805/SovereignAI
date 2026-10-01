const {chromium}=require('../frontend/llama-ui/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1920,height:990},serviceWorkers:'block'});
 const fixtures=Array.from({length:3},(_,i)=>({workspace_id:String(i+1).repeat(32),name:'Selection fixture '+(i+1),host_path:'C:/test-fixture/project-'+i,created_at:0,files:[],folders:[]}));
 let deletions=0;
 await page.route('**/coding/workspaces**',route=>{if(route.request().method()==='DELETE'){deletions++;return route.abort();}return route.fulfill({json:fixtures});});
 try{
 await page.goto('http://127.0.0.1:8088/#/');
 await page.getByRole('textbox',{name:'Chat message'}).waitFor();
 await page.evaluate(()=>window.dispatchEvent(new CustomEvent('sovereign-open-workspace',{detail:{tab:'code'}})));
 await page.getByRole('button',{name:'Manage workspaces',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'Manage workspaces'});
 const all=dialog.locator('.workspace-select-all input');
 await all.check();
 await dialog.getByRole('button',{name:'Delete selected (3)',exact:true}).waitFor();
 const rows=dialog.locator('.workspace-selection input');
 for(let i=0;i<3;i++){if(!await rows.nth(i).isChecked())throw Error('Selection state mismatch');}
 const visual=await rows.first().evaluate(el=>({background:getComputedStyle(el).backgroundColor,tick:getComputedStyle(el,'::after').content,padding:getComputedStyle(el).padding}));
 if(visual.tick==='none'||visual.padding!=='0px')throw Error('Invisible checkmark '+JSON.stringify(visual));
 await rows.first().uncheck();
 await dialog.getByRole('button',{name:'Delete selected (2)',exact:true}).waitFor();
 await all.check();await all.uncheck();
 if(!await dialog.getByRole('button',{name:'Delete selected (0)',exact:true}).isDisabled())throw Error('Empty selection enabled');
 await rows.first().check();await dialog.getByRole('button',{name:'Delete selected (1)',exact:true}).click();
 await dialog.getByText('Files are not moved to the Recycle Bin.',{exact:false}).waitFor();
 if(deletions)throw Error('Unexpected real delete');
 console.log(JSON.stringify({visual,selection:'individual, select all, deselect all passed',deletions}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
