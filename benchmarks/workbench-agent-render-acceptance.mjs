// Restore the actual installed-model vision answer recorded by the live acceptance.
// No inference response is mocked; this checks the history rendering path separately.
import { chromium } from '../frontend/llama-ui/node_modules/playwright/index.mjs';
import { readFile } from 'node:fs/promises';
const records = JSON.parse(await readFile('benchmarks/knowledge-context-acceptance/vision-results.json', 'utf8'));
const answer = records.find(r => r.routing?.capability === 'vision').answer;
const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true });
try {
 const context = await browser.newContext({ viewport: { width: 1366, height: 768 }, serviceWorkers: 'block' });
 const page = await context.newPage(); const errors = []; page.on('pageerror', e => errors.push(String(e)));
 await page.goto('http://127.0.0.1:8088');
 await page.evaluate(answer => sessionStorage.setItem('sovereign-agent-turns', JSON.stringify([{question: 'Which workspace is open in this screenshot? Describe only the visible interface.',answer,status:'completed'}])), answer);
 await page.getByRole('navigation', { name: 'Primary workbench navigation' }).getByRole('button', { name: 'Agent', exact: true }).click();
 await page.locator('.agent-answer strong').filter({ hasText: 'Summa' }).waitFor();
 if (await page.locator('.agent-answer li').count() !== 3) throw Error('Recorded model list did not render');
 if (errors.length) throw Error(errors.join('\n'));
 await page.screenshot({ path: 'benchmarks/knowledge-context-acceptance/agent-formatted-vision.png' });
 console.log(JSON.stringify({test:'Actual model answer restored from history renders emphasis and three list items',passed:true,pageErrors:errors}));
} finally { await browser.close(); }
