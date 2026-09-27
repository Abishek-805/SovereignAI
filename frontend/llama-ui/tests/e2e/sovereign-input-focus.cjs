const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
 const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
 const page = await browser.newPage({ viewport: { width: 1600, height: 900 }, colorScheme: 'dark' });
 page.setDefaultTimeout(25000);
 const results = [];
 async function check(label, locator) {
  await locator.focus();
  const style = await locator.evaluate(element => ({ active: document.activeElement === element, disabled: element.disabled || element.getAttribute('contenteditable') === 'false', outlineWidth: getComputedStyle(element).outlineWidth, outlineStyle: getComputedStyle(element).outlineStyle, boxShadow: getComputedStyle(element).boxShadow }));
  if ((!style.active && !style.disabled) || (style.outlineStyle !== 'none' && style.outlineWidth !== '0px') || style.boxShadow !== 'none') throw Error(`${label} still has a focus box: ${JSON.stringify(style)}`);
  results.push(label);
 }
 try {
  await page.goto('http://127.0.0.1:8088/#/');
  const nav = page.getByRole('navigation', { name: 'Primary workbench navigation' });
  const chatInput = page.locator('.chat-screen [data-slot="input-area"] textarea');
  await chatInput.waitFor();
  await check('Chat input', chatInput);
  await nav.getByRole('button', { name: 'Agent' }).click();
  await check('Agent task input', page.getByRole('textbox', { name: 'Task request' }));
  await page.screenshot({ path: path.resolve('../..', 'benchmarks/agent-input-focus.png') });
  await nav.getByRole('button', { name: 'Code' }).click();
  await check('Code assistant input', page.getByRole('textbox', { name: 'Coding task' }));
  await page.getByRole('region', { name: 'Coding workspace' }).getByRole('button', { name: 'Search files', exact: true }).click();
  await check('Code search input', page.getByRole('textbox', { name: 'Search project' }));
  await nav.getByRole('button', { name: 'Control Center' }).click();
  await page.getByRole('navigation', { name: 'Control Center sections' }).getByRole('button', { name: 'Knowledge' }).click();
  await page.getByRole('button', { name: 'Open document library' }).click();
  await check('Document question input', page.getByRole('textbox', { name: 'Document question' }));
  await check('Document search input', page.getByRole('textbox', { name: 'Find documents' }));
  fs.writeFileSync(path.resolve('../..', 'benchmarks/input-focus-browser.json'), JSON.stringify({ pass: true, checks: results }, null, 2));
  console.log('Input focus browser acceptance passed');
 } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
