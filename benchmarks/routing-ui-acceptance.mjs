// Display-edge fixtures only: these are deliberately synthetic telemetry, not router/model benchmarks.
// No generation endpoints are called. Run against the rebuilt production frontend.
import {chromium} from '../frontend/llama-ui/node_modules/playwright/index.mjs';
import {mkdir,writeFile} from 'node:fs/promises';
const base=process.env.SOVEREIGN_BASE||'http://127.0.0.1:8088',output='benchmarks/routing-ui-acceptance/';
await mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const checks=[],errors=[],generation=[];
const fixture={decision:{request_id:'display-fixture-not-measurement',intent:'general_question',capability:'text',modality:'text',candidate_models:['A-very-long-candidate-model-name-'.repeat(8)],candidate_rejection_reasons:{alternative:['unsupported_modality '+ 'A long factual rejection explanation. '.repeat(25)]},selected_model:'Qwen3-4B-Instruct-2507-Q4_K_M',route_reason:'Display fixture, not measured production routing. '+ 'Candidate fit explanation. '.repeat(30),required_context:2048,available_context:4096,resource_admission:{admitted:true},switch_required:false,classifier_time:0,routing_time:0.001,inference_time:null,model_load_time:null,fallback:null,errors:[],evidence_required:false,evidence_used:false,knowledge_scope:{connected:true,mode:'all',permitted_document_count:16},retrieval:{required:false,status:'not_required',document_count:0,passage_count:0,candidate_count:0},tools:[{name:'calculator',status:'completed',reason:'Synthetic display fixture, not a tool execution'}],failure_layer:'RESOURCE_FAILURE',validation:{status:'failed',checks:{syntax_valid:true,artifact_verified:false,private:null}},timings:{classification_ms:0,routing_ms:1,retrieval_ms:0,prefill_ms:null,generation_ms:null,validation_ms:0,total_ms:100},chain_of_thought:'must-not-render-private',events:[{event:'PRIVATE_INTERNAL',reason:'must-not-render-private'}]}};
const assert=(ok,message)=>{if(!ok)throw Error(message);};
try{
 for(const theme of ['dark','light'])for(const width of [1366,390]){
  const ctx=await browser.newContext({viewport:{width,height:844},serviceWorkers:'block'});
  await ctx.addInitScript(({fixture,theme})=>{localStorage.setItem('mode-watcher-mode',theme);sessionStorage.setItem('sovereign-agent-chat-id','display-edge-fixture');sessionStorage.setItem('sovereign-agent-turns',JSON.stringify([{question:'Display fixture',answer:'Synthetic public routing facts for UI checks.',status:'completed',routing:fixture}]));},{fixture,theme});
  const page=await ctx.newPage();page.on('pageerror',e=>errors.push(String(e)));page.on('request',r=>{if(/\/(?:agent\/jobs|documents\/jobs|(?:v1\/)?chat\/completions)$/.test(new URL(r.url()).pathname)&&r.method()==='POST')generation.push(r.url());});
  await page.goto(base);await page.locator('.sovereign-chat-form').waitFor();
  const nav=async(destination)=>{const back=page.getByRole('button',{name:'Go back',exact:true});if(await back.isVisible())await back.click();const expand=page.getByRole('button',{name:'Expand navigation',exact:true});if(width<768&&await expand.isVisible())await expand.click();await page.getByRole('navigation',{name:'Primary workbench navigation'}).getByRole('button',{name:destination,exact:true}).click();};
  await nav('Control Center');await page.getByRole('button',{name:'Appearance',exact:true}).click();await page.getByRole('button',{name:theme,exact:true}).click();
  await nav('Agent');

  const detail=page.locator('.assistant-message .route-details');await detail.waitFor();
  assert(!(await detail.getAttribute('open')),'Telemetry should be collapsed by default');await detail.locator('summary').click();
  const facts=detail.locator('.route-facts');await facts.waitFor();const text=await facts.innerText();
  assert(text.includes('0.000 s')&&text.includes('0.001 s')&&text.includes('No'),'Measured zero/false fixture fields disappeared');
  assert(!text.includes('Inference time')&&!text.includes('Model load time')&&!text.includes('Fallback')&&!text.includes('Prefill time')&&!text.includes('Generation time'),'Unknown telemetry was fabricated');
  assert(text.includes('unsupported_modality')&&text.includes('Display fixture, not measured production routing.'),'Backend facts/rejections were lost');
  assert(text.includes('Not used')&&text.includes('16 permitted documents')&&text.includes('0 documents · 0 passages'),'Permission/evidence/retrieval distinctions missing');assert(text.includes('RESOURCE_FAILURE')&&text.includes('artifact_verified'),'Failure and validation facts missing');assert(!text.includes('must-not-render-private')&&!text.includes('PRIVATE_INTERNAL'),'Internal log or thought leaked');
  const bounds=await facts.boundingBox();assert(bounds.x>=-1&&bounds.x+bounds.width<=width+1,'Route details overflow viewport');
  assert(await facts.evaluate(el=>el.scrollWidth<=el.clientWidth+1),'Long telemetry causes horizontal overflow');
  await page.screenshot({path:output+`agent-details-${theme}-${width}.png`});
  await detail.locator('summary').click();await page.getByRole('button',{name:'Model and routing',exact:true}).click();
  const popup=page.getByRole('dialog',{name:'Model and routing details'});await popup.waitFor();const pop=await popup.boundingBox();assert(pop.x>=-1&&pop.x+pop.width<=width+1,'Model status popup overflow');await page.screenshot({path:output+`model-status-${theme}-${width}.png`});
  await page.getByRole('button',{name:'Model and routing',exact:true}).click();
  for(const destination of ['Chat','Code','Knowledge','Control Center']){
   await nav(destination);
   await page.screenshot({path:output+`${destination.toLowerCase().replace(' ','-')}-${theme}-${width}.png`});
  }
  checks.push({test:`Synthetic RouteDetails truth, wrapping and preserved pages ${theme} ${width}`,passed:true});await ctx.close();
 }
 assert(!errors.length,errors.join('\n'));assert(!generation.length,'Unexpected model call');
 const result={scope:'Synthetic display-edge fixtures only; no inference/model selection metrics',checks,pageErrors:errors,generationRequests:generation};await writeFile(output+'results.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
}finally{await browser.close();}
