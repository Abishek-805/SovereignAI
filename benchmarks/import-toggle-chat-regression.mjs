// Real browser and local model, isolated browser history; no user project writes.
import { chromium } from '../frontend/llama-ui/node_modules/playwright/index.mjs';
import { mkdir, writeFile } from 'node:fs/promises';
const base = 'http://127.0.0.1:8088';
const output = 'benchmarks/import-toggle-chat-regression' + (process.env.ACCEPTANCE_SUFFIX || '') + '/';
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true });
const checks = [], errors = [], requests = [];
const ensure = (value, message) => { if (!value) throw Error(message); };
try {
 const context = await browser.newContext({ viewport: { width: 1366, height: 844 }, serviceWorkers: 'block' });
 const page = await context.newPage();
 page.on('pageerror', error => errors.push(String(error)));
 page.on('request', request => { if (/\/(agent\/jobs|documents\/jobs|v1\/chat\/completions)$/.test(new URL(request.url()).pathname)) requests.push({ url: request.url(), at: Date.now() }); });
 await page.goto(base);
 const chat = page.locator('.sovereign-chat-form');
 await chat.waitFor();
 const toggle = chat.getByRole('switch', { name: 'Connect Knowledge' });
 ensure(await toggle.getAttribute('aria-checked') === 'true', 'Knowledge should default on');
 const started = Date.now();
 const chatResponsePromise = page.waitForResponse(response => response.url().endsWith('/documents/jobs') && response.request().method() === 'POST');
 await chat.getByRole('textbox').fill('What is your name?');
 await chat.getByRole('textbox').press('Enter');
 const answer = page.locator('.chat-message-assistant').last();
 await answer.waitFor();
 await page.waitForFunction(() => Array.from(document.querySelectorAll('.chat-message-assistant')).some(node => /SovereignAI/i.test(node.textContent || '') && !/Processing\.\.\./.test(node.textContent || '')), null, { timeout: 120000 });
 const elapsed = (Date.now() - started) / 1000;
 const chatAdmission = await (await chatResponsePromise).json();
 const chatJob = await (await page.request.get(base + '/coding/jobs/' + chatAdmission.job_id)).json();
 ensure(chatJob.state === 'completed' && chatJob.result?.status === 'conversation' && chatJob.result.sources?.length === 0, 'Identity request retrieved documents instead of answering normally');
 ensure(await page.locator('.knowledge-message-scope').count() === 0, 'Repeated document list remains in Chat');
 await toggle.click();
 ensure(await toggle.getAttribute('aria-checked') === 'false', 'Knowledge did not disconnect after answer history');
 ensure(!/DataCloneError/.test(await page.locator('body').innerText()), 'IndexedDB clone failure after toggle');
 await page.reload(); await chat.waitFor();
 ensure(await toggle.getAttribute('aria-checked') === 'false', 'Knowledge off was not persisted');
 checks.push({ test: 'Actual identity answer with Knowledge on; toggle off with populated history persists without clone error', elapsed_seconds: elapsed, model_requests: requests.slice(), job: chatJob });
 await page.screenshot({ path: output + 'chat.png' });
 await page.getByRole('navigation', { name: 'Primary workbench navigation' }).getByRole('button', { name: 'Agent', exact: true }).click();
 const input = page.getByLabel('Task request'); await input.fill('What is your name?');
 const responsePromise = page.waitForResponse(response => response.url().endsWith('/agent/jobs') && response.request().method() === 'POST');
 await input.press('Enter'); const admitted = await responsePromise; ensure(admitted.ok(), await admitted.text());
 const admittedJob = await admitted.json();
 let job;
 for (let i = 0; i < 120; i++) {
  job = await (await page.request.get(base + '/coding/jobs/' + admittedJob.job_id)).json();
  if (job.state !== 'running') break;
  await page.waitForTimeout(500);
 }
 ensure(job?.state === 'completed' && job.result?.plan?.action === 'answer', 'Agent identity request did not finish as an answer: ' + JSON.stringify(job));
 await page.locator('.agent-answer').filter({ hasText: /SovereignAI/i }).waitFor();
 ensure(await page.locator('.agent-answer .route-details').count() === 0, 'Technical route details remain in Agent');
 checks.push({ test: 'Agent identity response completes without visible route panel', elapsed_seconds: job.elapsed, route: job.result.routing?.decision });
 await page.screenshot({ path: output + 'agent.png' });
 ensure(errors.length === 0, errors.join('\n'));
 await writeFile(output + 'results.json', JSON.stringify({ checks, errors }, null, 2));
 console.log(JSON.stringify({ passed: checks.length, errors, chat_identity_seconds: elapsed }));
} finally { await browser.close(); }
