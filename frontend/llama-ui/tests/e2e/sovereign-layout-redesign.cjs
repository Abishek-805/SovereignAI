const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
 const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
 const page = await browser.newPage({ viewport: { width: 1600, height: 900 }, colorScheme: 'dark' });
 const errors = [];
 page.on('pageerror', error => errors.push(error.stack || String(error)));
 page.setDefaultTimeout(25000);
 try {
  await page.goto('http://127.0.0.1:8088/#/');
  const nav = page.getByRole('navigation', { name: 'Primary workbench navigation' });
  await nav.getByRole('button', { name: 'Agent' }).click();
  const agent = page.getByLabel('Local agent');
  await agent.getByRole('textbox', { name: 'Task request' }).waitFor();
  if (await agent.getByRole('combobox').count()) throw Error('Native project select remained in composer');
  const projectTrigger = agent.getByRole('button', { name: 'Project context' });
  await projectTrigger.click();
  await agent.getByRole('heading', { name: 'Let’s get it done.' }).click();
  if (await agent.getByRole('group', { name: 'Select project' }).count() || await projectTrigger.getAttribute('aria-expanded') !== 'false') throw Error('Project menu did not close on outside click');
  await projectTrigger.click();
  await page.keyboard.press('Escape');
  if (await agent.getByRole('group', { name: 'Select project' }).count() || !await agent.isVisible()) throw Error('Escape did not close only the project menu');
  await projectTrigger.click();
  await agent.getByRole('group', { name: 'Select project' }).getByRole('button', { name: 'No project' }).click();
  const examples = await agent.locator('.examples').boundingBox();
  const composer = await agent.locator('.composer').boundingBox();
  if (!examples || !composer || Math.abs(examples.x - composer.x) > 3 || Math.abs(examples.width - composer.width) > 5) throw Error('Agent cards and composer are misaligned');
  const modelBox = await page.getByRole('button', { name: 'Model and routing' }).boundingBox();
  const backBox = await page.getByRole('button', { name: 'Go back' }).boundingBox();
  if (!modelBox || !backBox || backBox.x + backBox.width + 8 > modelBox.x) throw Error('Header controls overlap');
  const modelButton = page.getByRole('button', { name: 'Model and routing' });
  await modelButton.hover();
  await page.waitForTimeout(220);
  if (await modelButton.evaluate(element => getComputedStyle(element).transform) === 'none') throw Error('Model selector hover treatment missing');
  await page.screenshot({ path: path.resolve('../..', 'benchmarks/model-router-hover.png') });
  await modelButton.click();
  await page.getByRole('dialog', { name: 'Model and routing details' }).waitFor();
  await modelButton.click();
  await page.screenshot({ path: path.resolve('../..', 'benchmarks/agent-redesign.png') });
  await nav.getByRole('button', { name: 'Code' }).click();
  const ide = page.getByRole('region', { name: 'Coding workspace' });
  await ide.waitFor();
  const workspacePicker = ide.getByLabel('Open coding workspace');
  if (await workspacePicker.locator('option').count() > 1) await workspacePicker.selectOption({ index: 1 });
  if (await ide.getByLabel('New workspace name').count()) throw Error('New-project form remained in toolbar');
  if (await ide.getByRole('textbox', { name: 'Search project' }).count()) throw Error('Search field remained in Explorer');
  const searchButton = ide.getByRole('button', { name: 'Search files', exact: true });
  await searchButton.click();
  if (await searchButton.getAttribute('aria-pressed') !== 'true') throw Error('Search state not visible');
  const searchInput = ide.getByRole('textbox', { name: 'Search project' });
  if (!await searchInput.evaluate(element => element === document.activeElement)) throw Error('Search did not stay in Explorer');
  if (await page.getByRole('dialog', { name: 'Quick open' }).count()) throw Error('Search opened the Quick Open overlay');
  const id = await workspacePicker.inputValue();
  if (id) {
   const project = await (await page.request.get(`http://127.0.0.1:8088/coding/workspaces/${encodeURIComponent(id)}`)).json();
   if (project.files.length) {
    await searchInput.fill(project.files[0].name);
    await ide.locator('.search-hit').first().waitFor();
    const source = await (await page.request.get(`http://127.0.0.1:8088/coding/workspaces/${encodeURIComponent(id)}/files/${encodeURIComponent(project.files[0].name)}`)).json();
    const token = source.content.match(/[A-Za-z_]{5,}/)?.[0];
    if (token) { await searchInput.fill(token); await ide.locator('.search-hit').first().waitFor(); }
   }
  }
  await page.screenshot({ path: path.resolve('../..', 'benchmarks/code-search-redesign.png') });
  await ide.getByRole('button', { name: 'Show Explorer' }).click();
  if (await searchInput.count()) throw Error('Search field remained after returning to Explorer');
  const output = ide.getByRole('region', { name: 'Code output' });
  const handle = ide.getByRole('button', { name: 'Resize terminal. Drag or use arrow keys' });
  const before = await output.boundingBox();
  await handle.focus();
  await page.keyboard.press('ArrowUp');
  const after = await output.boundingBox();
  if (!before || !after || after.height <= before.height) throw Error('Terminal did not resize');
  const grip = await handle.boundingBox();
  if (!grip) throw Error('Terminal resize handle missing');
  await page.mouse.move(grip.x + grip.width / 2, grip.y + grip.height / 2);
  await page.mouse.down();
  await page.mouse.move(grip.x + grip.width / 2, grip.y - 35, { steps: 5 });
  await page.mouse.up();
  const dragged = await output.boundingBox();
  if (!dragged || dragged.height <= after.height) throw Error('Terminal pointer drag did not resize');
  const explorerToggle = ide.getByRole('button', { name: 'Toggle Explorer' });
  await explorerToggle.click();
  if (await explorerToggle.getAttribute('aria-pressed') !== 'false') throw Error('Explorer toggle state not visible');
  await explorerToggle.click();
  await page.screenshot({ path: path.resolve('../..', 'benchmarks/code-redesign.png') });
  await page.keyboard.press('Control+p');
  await page.getByRole('dialog', { name: 'Quick open' }).waitFor();
  await page.keyboard.press('Escape');
  if (await page.getByRole('dialog', { name: 'Quick open' }).isVisible()) throw Error('Quick open did not close');
  if (errors.length) throw Error(errors.join('\n'));
  const report = { pass: true, checks: ['agent cards and composer alignment', 'project menu closes on outside click and Escape', 'header controls do not overlap', 'model selector hover and expanded state', 'no always-visible new project form', 'search stays in Explorer and finds names and code', 'toggle pressed states', 'keyboard and pointer terminal resize', 'Ctrl+P quick open', 'no page errors'], pageErrors: errors };
  fs.writeFileSync(path.resolve('../..', 'benchmarks/layout-redesign-browser.json'), JSON.stringify(report, null, 2));
  console.log('Layout redesign browser acceptance passed');
 } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
