const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const base = 'http://127.0.0.1:8088';
const out = path.resolve(__dirname, '../../../../outputs/product-verification-20261004/browser-' + Date.now());
fs.mkdirSync(out, { recursive: true });
const save = (name, data) => fs.writeFileSync(path.join(out, name + '.json'), JSON.stringify(data, null, 2));

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const api = async (url, body, method) => {
    const response = await context.request.fetch(base + url, { method: method || (body ? 'POST' : 'GET'), data: body, timeout: 240000 });
    const value = await response.json();
    if (!response.ok()) throw new Error(JSON.stringify(value));
    return value;
  };
  try {
    const workspace = await api('/coding/workspaces', { name: 'Product verification CLI ' + Date.now() });
    save('workspace', workspace);
    await context.addInitScript(id => localStorage.setItem('sovereign-active-workspace', id), workspace.workspace_id);
    await page.goto(base + '/#/');
    await page.getByRole('button', { name: 'Agent', exact: true }).first().click();
    await page.getByRole('textbox', { name: 'Task request' }).waitFor();
    const knowledge = page.getByLabel('Local agent').getByRole('switch', { name: 'Connect Knowledge' });
    if (await knowledge.getAttribute('aria-checked') === 'true') await knowledge.click();
    await page.getByRole('textbox', { name: 'Task request' }).fill('Create a Python CLI project with main.py, helpers.py and README.md. Define helpers.answer() returning 42. main.py must import answer from helpers and print its return value. Do not create other files.');
    const admission = page.waitForResponse(r => r.url().endsWith('/agent/jobs') && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Send task', exact: true }).click();
    const job = await (await admission).json();
    save('creation-admission', job);
    await page.waitForFunction(id => sessionStorage.getItem('sovereign-agent-job') === id, job.job_id);
    const before = await api('/coding/jobs/' + job.job_id);
    if (before.state !== 'running') throw new Error('Task finished before disconnect test');
    await context.setOffline(true);
    await page.waitForTimeout(3500);
    const preserved = await page.evaluate(() => ({ job: sessionStorage.getItem('sovereign-agent-job'), turns: JSON.parse(sessionStorage.getItem('sovereign-agent-turns') || '[]') }));
    if (preserved.job !== job.job_id || !preserved.turns.some(t => t.status === 'working')) throw new Error('Disconnect discarded task state');
    await context.setOffline(false);
    await page.reload();
    await page.getByRole('button', { name: 'Agent', exact: true }).first().click();
    await page.getByRole('textbox', { name: 'Task request' }).waitFor();
    const restored = await page.evaluate(() => sessionStorage.getItem('sovereign-agent-job'));
    if (restored !== job.job_id) throw new Error('Reload lost original job ID');
    let final;
    for (let n = 0; n < 900; n++) {
      final = await api('/coding/jobs/' + job.job_id);
      if (final.state !== 'running') break;
      await page.waitForTimeout(1000);
    }
    save('creation-final', final);
    if (final.state !== 'completed') throw new Error('Creation failed: ' + JSON.stringify(final));
    await page.waitForFunction(() => sessionStorage.getItem('sovereign-agent-job') === null, null, { timeout: 15000 });
    const display = await page.getByLabel('Local agent').innerText();
    save('browser-reconnect', { before, preserved, restored, job_id: job.job_id, final_state: final.state, display });
    await page.screenshot({ path: path.join(out, 'reconnect-completed.png') });
    const accept = page.getByRole('button', { name: 'Accept changes', exact: true }).last();
    if (await accept.count()) {
      const accepted = page.waitForResponse(r => r.url().endsWith('/accept') && r.request().method() === 'POST');
      await accept.click();
      if (!(await accepted).ok()) throw new Error('Accept failed');
    }
    const actualWorkspace = final.result.workspace_id || final.result.result?.workspace_id;
    const acceptedWorkspace = await api('/coding/workspaces/' + actualWorkspace);
    save('accepted-workspace', acceptedWorkspace);
    const names=acceptedWorkspace.files.map(f=>f.name).sort();
    if(JSON.stringify(names)!==JSON.stringify(['README.md','helpers.py','main.py']))throw new Error('Requested file coverage mismatch: '+names);
    const check=await api('/coding/workspaces/'+actualWorkspace+'/jobs',{kind:'terminal',command:"python -c 'from helpers import answer; import subprocess,sys; assert answer() == 42; assert isinstance(answer(), int); output=subprocess.check_output([sys.executable, \"main.py\"], text=True); assert output.strip() == \"42\", output; print(output, end=\"\")'"});
    let validation;
    for(let n=0;n<90;n++){
      validation=await api('/coding/jobs/'+check.job_id);
      if(validation.state!=='running')break;
      await page.waitForTimeout(1000);
    }
    save('independent-validation',validation);
    if(validation.state!=='completed'||validation.result.exit_code!==0||!validation.result.stdout.includes('42'))throw new Error('Independent project check failed');
    console.log('Live browser reconnect and project creation completed; evidence saved.');
  } finally { await browser.close(); }
})().catch(error => { save('browser-error', { error: String(error), stack: error.stack }); console.error(error); process.exitCode = 1; });
