// Live backend acceptance against installed models and existing user data.
// Does not create or modify code files or documents.
import {writeFile} from 'node:fs/promises';
const base='http://127.0.0.1:8088';
const checks=[];
async function json(path,body){const response=await fetch(base+path,body===undefined?{}:{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});const result=await response.json();if(!response.ok)throw Error(response.status+': '+JSON.stringify(result));return result;}
async function job(goal,document_ids=[],workspace_id=null,history=[]){const started=await json('/agent/jobs',{goal,document_ids,workspace_id,history});let result;do{await new Promise(resolve=>setTimeout(resolve,500));result=await json('/coding/jobs/'+started.job_id);}while(result.state==='running');if(result.state!=='completed')throw Error(JSON.stringify(result));return result;}
const documents=await json('/documents');const workspaces=await json('/coding/workspaces');
const workspace=workspaces.find(item=>item.name==='Summa')||workspaces[0];
const before=workspace?await json('/coding/workspaces/'+workspace.workspace_id):null;
const histories=[];
for(const question of ['hi','hay','whats up?','whats your name','What is a prime number?']){
 const result=await job(question,documents.slice(0,2).map(doc=>doc.document_id),workspace?.workspace_id,histories.slice(-8));
 if(result.result.plan.action!=='answer'||result.events.some(event=>/Reading project|Retrieving|Reading selected/.test(event.stage)))throw Error('Conversational request opened files: '+question+' '+JSON.stringify(result));
 if(!result.result.answer?.trim())throw Error('Empty model answer');
 histories.push('User: '+question,'Assistant: '+result.result.answer);
 checks.push({question,action:result.result.plan.action,answer:result.result.answer,elapsed:result.elapsed});
}
if(workspace){const after=await json('/coding/workspaces/'+workspace.workspace_id);if(JSON.stringify(before.files)!==JSON.stringify(after.files))throw Error('Conversation modified project');}
const selected=documents.filter(doc=>/inspection.txt|sop.txt/.test(doc.display_name)).slice(0,2);
if(selected.length){const response=await json('/ask',{question:'Summarize all connected documents.',document_ids:selected.map(doc=>doc.document_id)});if(!response.coverage||response.coverage.covered_documents!==selected.length||!response.sources?.length)throw Error('Collection coverage failed '+JSON.stringify(response));checks.push({question:'Summarize all connected documents.',status:response.status,answer:response.answer,coverage:response.coverage});}
await writeFile('benchmarks/backend-live-results.json',JSON.stringify({checks},null,2));console.log(JSON.stringify({checks},null,2));
