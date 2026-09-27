const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
 const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
 const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark' });
 const errors = [];
  page.on('pageerror', error => errors.push(error.stack || String(error)));
 page.setDefaultTimeout(25000);
 try {
  const facts = await (await page.request.get('http://127.0.0.1:8088/workbench/info')).json();
  await page.goto('http://127.0.0.1:8088/#/');
  const nav = page.getByRole('navigation', { name: 'Primary workbench navigation' });
  for (const label of ['Chat', 'Agent', 'Code', 'Control Center']) await nav.getByRole('button', { name: label, exact: true }).waitFor();
  if (await nav.getByRole('button').count() !== 4) throw Error('Primary navigation has more than four modes');
  await page.getByRole('button', { name: 'Model and routing' }).click();
  const popover = page.getByRole('dialog', { name: 'Model and routing details' });
  await popover.getByText('Automatic', { exact: true }).waitFor();
  await popover.getByText(facts.runtime.generator.available ? facts.models.find(model => model.alias === facts.runtime.generator.alias)?.model_id || facts.runtime.generator.alias : 'No model running').first().waitFor();
  await popover.getByText(facts.models[0].model_id).first().waitFor();
  if (!await popover.getByText('A separate coding model is not installed.', { exact: false }).isVisible()) throw Error('Coding route disclosure missing');
  await page.screenshot({ path: path.resolve('../..', 'benchmarks/four-mode-routing.png') });
  await page.getByRole('button', { name: 'Model and routing' }).click();
  await nav.getByRole('button', { name: 'Control Center' }).click();
  await page.getByText('Current model', { exact: true }).waitFor();
  for (const section of ['Models & routing', 'Knowledge', 'Runtime', 'System & downloads', 'Appearance']) {
   await page.getByRole('navigation', { name: 'Control Center sections' }).getByRole('button', { name: section }).click();
  }
  await page.screenshot({ path: path.resolve('../..', 'benchmarks/four-mode-control-center.png') });
  await page.getByRole('navigation', { name: 'Control Center sections' }).getByRole('button', { name: 'Knowledge' }).click();
  await page.getByRole('button', { name: 'Open document library' }).click();
  await page.getByRole('heading', { name: 'Documents', exact: true }).waitFor();
  await nav.getByRole('button', { name: 'Code', exact: true }).click();
  await page.getByRole('region', { name: 'Coding workspace', exact: true }).waitFor();
  await nav.getByRole('button', { name: 'Agent', exact: true }).click();
  await page.getByLabel('Local agent').waitFor();
  await nav.getByRole('button', { name: 'Chat', exact: true }).click();
  if (await page.getByLabel('SovereignAI workbench').isVisible()) throw Error('Chat did not close the workbench');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Model and routing' }).focus();
  await page.keyboard.press('Enter');
  await popover.waitFor();
  const bounds = await popover.boundingBox();
  if (!bounds || bounds.x < 0 || bounds.x + bounds.width > 391) throw Error('Routing popover overflows mobile viewport');
  await page.screenshot({ path: path.resolve('../..', 'benchmarks/four-mode-routing-mobile.png') });
  await page.keyboard.press('Escape');
  if (await popover.isVisible()) throw Error('Escape did not close model details');
  await page.route('**/status', route => route.abort());
  await page.route('**/workbench/info', route => route.abort());
  await page.reload();
  await page.getByRole('button', { name: 'Model and routing' }).getByText('Local backend disconnected').waitFor();
  if (errors.length) throw Error(errors.join('\n'));
  const report = { pass: true, routes: facts.routing.routes, registeredModels: facts.models.map(model => ({ capability: model.capability, alias: model.alias, assets_present: model.assets_present })), checks: ['four primary destinations','live model registry and automatic route display','Control Center sections','contextual document entry','Chat closes workbench','mobile popover bounds and keyboard dismissal','disconnected runtime state'], pageErrors: errors };
  fs.writeFileSync(path.resolve('../..', 'benchmarks/four-mode-browser.json'), JSON.stringify(report, null, 2));
  console.log('Four-mode browser acceptance passed');
 } catch (error) {
  await page.screenshot({ path: path.resolve('../..', 'benchmarks/four-mode-failure.png') });
  throw error;
 } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
