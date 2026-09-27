const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
 const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
 const page = await browser.newPage({ viewport: { width: 1918, height: 910 }, colorScheme: 'dark' });
 const errors = [];
 page.on('pageerror', error => errors.push(error.stack || String(error)));
 page.setDefaultTimeout(25000);
 try {
  await page.goto('http://127.0.0.1:8088/#/');
  const heading = page.getByRole('heading', { name: 'What are we working on?' });
  await heading.waitFor();
  for (const height of [910, 650]) {
   await page.setViewportSize({ width: 1918, height });
   await page.waitForTimeout(350);
   const bounds = await heading.boundingBox();
   await page.screenshot({ path: path.resolve('../..', `benchmarks/chat-webview-${height}.png`) });
   if (!bounds || bounds.y < 20 || bounds.y + bounds.height > height) {
    const layout = await heading.evaluate(element => { const nodes = [element, element.parentElement, element.parentElement?.parentElement, element.parentElement?.parentElement?.parentElement]; return nodes.map(node => node && ({ tag: node.tagName, className: node.className, transform: getComputedStyle(node).transform, position: getComputedStyle(node).position, bounds: node.getBoundingClientRect().toJSON() })); });
    throw Error(`Chat heading clipped at ${height}px: ${JSON.stringify(bounds)} ${JSON.stringify(layout)}`);
   }
  }
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.getByRole('navigation', { name: 'Primary workbench navigation' }).getByRole('button', { name: 'Code' }).click();
  const ide = page.getByRole('region', { name: 'Coding workspace' });
  await ide.waitFor();
  const picker = ide.getByLabel('Open coding workspace');
  if (await picker.locator('option').count() > 1) await picker.selectOption({ index: 1 });
  const before = await picker.inputValue();
  await ide.getByRole('button', { name: 'Enter full screen code' }).click();
  await ide.getByRole('button', { name: 'Exit full screen code' }).waitFor();
  if (!await page.evaluate(() => document.body.classList.contains('sovereign-code-focus'))) throw Error('Code focus state not set');
  const full = await ide.evaluate(element => { const box = element.getBoundingClientRect(); return { x: box.x, y: box.y, width: box.width, height: box.height, viewportWidth: innerWidth, viewportHeight: innerHeight }; });
  if (full.x !== 0 || full.y !== 0 || Math.abs(full.width - full.viewportWidth) > 1 || Math.abs(full.height - full.viewportHeight) > 1) throw Error(`IDE did not fill viewport: ${JSON.stringify(full)}`);
  if (await picker.inputValue() !== before) throw Error('Workspace changed on entering full screen');
  await page.screenshot({ path: path.resolve('../..', 'benchmarks/code-focus-fullscreen.png') });
  await ide.getByRole('button', { name: 'Exit full screen code' }).click();
  await ide.getByRole('button', { name: 'Enter full screen code' }).waitFor();
  if (await picker.inputValue() !== before) throw Error('Workspace changed on leaving full screen');
  await ide.getByRole('button', { name: 'Enter full screen code' }).click();
  await page.keyboard.press('Escape');
  await ide.getByRole('button', { name: 'Enter full screen code' }).waitFor();
  if (!await page.getByRole('button', { name: 'Go back' }).isVisible()) throw Error('Escape closed Code instead of full screen');
  await ide.evaluate(element => { element.requestFullscreen = () => Promise.reject(new Error('Fullscreen unavailable in embedded browser')); });
  await ide.getByRole('button', { name: 'Enter full screen code' }).click();
  await ide.getByRole('button', { name: 'Exit full screen code' }).waitFor();
  if (await page.evaluate(() => document.fullscreenElement !== null)) throw Error('Embedded-browser fallback was not used');
  const fallback = await ide.boundingBox();
  if (!fallback || fallback.x !== 0 || fallback.y !== 0 || Math.abs(fallback.width - 1600) > 1 || Math.abs(fallback.height - 900) > 1) throw Error(`Embedded-browser focus did not fill the viewport: ${JSON.stringify(fallback)}`);
  await ide.getByRole('button', { name: 'Exit full screen code' }).click();
  if (errors.length) throw Error(errors.join('\n'));
  fs.writeFileSync(path.resolve('../..', 'benchmarks/code-focus-browser.json'), JSON.stringify({ pass: true, checks: ['chat greeting visible at normal and short viewport heights', 'IDE fills viewport', 'workspace persists', 'button exits focus', 'Escape exits focus without closing Code', 'embedded-browser viewport fallback'], pageErrors: errors }, null, 2));
  console.log('Code focus and web-view browser acceptance passed');
 } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
