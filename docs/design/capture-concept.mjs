import { chromium } from '../../frontend/llama-ui/node_modules/playwright-core/index.mjs';
const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:900}});
await page.goto('file:///C:/Users/ashek/Desktop/SovereignAI/docs/design/workbench-concept.html');
for(const name of ['chat','knowledge','agent','code','control']){await page.evaluate(name=>showPage(name),name);await page.waitForTimeout(150);await page.screenshot({path:`docs/design/${name}-desktop.png`}); console.log(name, await page.evaluate(()=>({width:document.documentElement.scrollWidth,viewport:innerWidth,height:document.documentElement.scrollHeight,viewportHeight:innerHeight})));}
await page.setViewportSize({width:390,height:844});
for(const name of ['chat','knowledge','agent','control']){await page.evaluate(name=>showPage(name),name);await page.waitForTimeout(150);await page.screenshot({path:`docs/design/${name}-mobile.png`}); console.log(name+'-mobile',await page.evaluate(()=>({width:document.documentElement.scrollWidth,viewport:innerWidth,height:document.documentElement.scrollHeight,viewportHeight:innerHeight})));}
await page.setViewportSize({width:1440,height:900});await page.evaluate(()=>{document.body.classList.add('light');showPage('knowledge')});await page.waitForTimeout(180);await page.mouse.move(0,0);await page.screenshot({path:'docs/design/knowledge-light.png'});await browser.close();
