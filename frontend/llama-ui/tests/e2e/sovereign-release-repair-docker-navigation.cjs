const {chromium}=require('playwright'),fs=require('node:fs'),path=require('node:path');
(async()=>{const out=path.resolve(__dirname,'../../../../outputs/release-repair'),b=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'}),p=await b.newPage();try{
 await p.goto('http://127.0.0.1:8088/#/');
 const fixture=JSON.parse(fs.readFileSync(path.join(out,'agent/AT-13-oracle.json'))),wid=fixture.workspace_id;
 const admitted=await(await p.request.post(`http://127.0.0.1:8088/coding/workspaces/${wid}/jobs`,{data:{kind:'terminal',command:'python -c "import time; time.sleep(8); print(42)"'}})).json();
 const get=async()=>await(await p.request.get('http://127.0.0.1:8088/coding/jobs/'+admitted.job_id)).json();
 const before=await get();const nav=p.getByRole('navigation',{name:'Primary workbench navigation'});
 await nav.getByRole('button',{name:'Code',exact:true}).click();await nav.getByRole('button',{name:'Chat',exact:true}).click();await p.reload();const afterReload=await get();
 const concurrent=await p.request.post('http://127.0.0.1:8088/v1/chat/completions',{data:{model:'sovereign-text',messages:[{role:'user',content:'Hello'}],stream:false}});
 let final;for(let i=0;i<60;i++){final=await get();if(final.state!=='running')break;await p.waitForTimeout(1000)}
 const checks={started:before.state==='running',preservedAfterReload:afterReload.job_id===admitted.job_id,busyResponse:concurrent.status()===409,completed:final.state==='completed'&&final.result.exit_code===0&&final.result.stdout.includes('42')};
 fs.writeFileSync(path.join(out,'persistence/docker-navigation.json'),JSON.stringify({admitted,before,afterReload,concurrent:{status:concurrent.status(),body:await concurrent.text()},final,checks,status:Object.values(checks).every(Boolean)?'PASS':'FAIL'},null,2));console.log(checks);
}finally{await b.close()}})().catch(e=>{console.error(e);process.exitCode=1});
