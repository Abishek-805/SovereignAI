// Manual local browser smoke for the explicit Agent entry. Requires the workbench on 8088.
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    await page.goto('http://127.0.0.1:8088/#/', { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: 'New task', exact: true }).click();
    await page.getByLabel('Describe your task').fill('Calculate: (8.2 - 7.1) * 2');
    await page.getByRole('button', { name: /Start task/ }).click();
    await page.getByText('Task details · completed', { exact: true }).click();
    await page.getByLabel('Agent execution').getByText(/CALCULATION/).waitFor({ timeout: 30000 });
    const text = await page.locator('#sovereign-documents').innerText();
    if (!text.includes('2.2') || !text.includes('Status: COMPLETED') || !text.includes('no model')) {
      throw new Error('Agent calculation result or route is missing: ' + text.slice(-800));
    }
    await page.getByText('View activity & tool steps', {exact:true}).click();
    await page.getByLabel('Agent activity').waitFor();
    await page.getByText(/Steps 1\/8/).waitFor();
    console.log('Agent browser smoke passed: calculation, route and completed state visible.');
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
