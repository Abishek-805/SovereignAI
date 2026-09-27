const { chromium } = require('playwright');
const path = require('node:path');

(async () => {
 const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
 const page = await browser.newPage({ viewport: { width: 1600, height: 900 }, colorScheme: 'dark' });
 page.setDefaultTimeout(20000);
 const errors = [];
 page.on('pageerror', error => errors.push(String(error)));
 try {
  await page.goto('http://127.0.0.1:8088/#/');
  await page.getByRole('navigation', { name: 'Primary workbench navigation' }).getByRole('button', { name: 'Control Center' }).click();
  await page.getByRole('navigation', { name: 'Control Center sections' }).getByRole('button', { name: 'System & downloads' }).click();
  await page.getByRole('button', { name: 'View validated downloads' }).click();
  const downloads = page.getByRole('region', { name: 'Validated artifacts' });
  await downloads.waitFor();
  const cards = downloads.locator('.download-card');
  await cards.nth(1).waitFor();
  if (await cards.count() < 2) throw Error('Need two artifacts to verify grid layout');
  const first = await cards.nth(0).boundingBox(), second = await cards.nth(1).boundingBox();
  if (!first || !second || Math.abs(first.y - second.y) > 3 || second.x <= first.x + first.width - 3) throw Error('Downloads are not side by side on desktop');
  const api = await (await page.request.get('http://127.0.0.1:8088/workbench/artifacts')).json();
  const stamp = item => typeof item.created_at === 'number' ? item.created_at * 1000 : Date.parse(item.created_at || '') || 0;
  const expected = [...api].sort((a, b) => stamp(b) - stamp(a));
  const firstName = await cards.first().locator('.download-file-info strong').textContent();
  if (firstName !== expected[0].name) throw Error('Newest artifact is not first');
  const link = cards.first().getByRole('link', { name: `Download ${firstName}` });
  if (!await link.isVisible() || await link.getAttribute('href') !== expected[0].url) throw Error('Validated download action missing');
  const fileResponse = await page.request.get('http://127.0.0.1:8088' + expected[0].url);
  if (!fileResponse.ok()) throw Error('Download link did not return the validated file');
  await page.screenshot({ path: path.resolve('../..', 'benchmarks/downloads-two-column.png') });
  await downloads.getByRole('button', { name: 'Refresh downloads' }).click();
  await cards.first().waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  const mobileFirst = await cards.nth(0).boundingBox(), mobileSecond = await cards.nth(1).boundingBox();
  if (!mobileFirst || !mobileSecond || mobileSecond.y <= mobileFirst.y) throw Error('Downloads did not stack on mobile');
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)) throw Error('Downloads overflow mobile viewport');
  await page.screenshot({ path: path.resolve('../..', 'benchmarks/downloads-mobile.png') });
  if (errors.length) throw Error(errors.join('\n'));
  console.log('Downloads order, two-column desktop, actions, refresh, and mobile layout passed');
 } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
