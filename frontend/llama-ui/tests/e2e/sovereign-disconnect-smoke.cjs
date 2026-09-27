// Manual smoke: start the local test backend, run this file, then stop that
// backend when "ready_for_disconnect" appears. No model is required.
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  try {
    await page.goto('http://127.0.0.1:8088/#/', { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: 'Documents' }).click();
    console.log('ready_for_disconnect');
    await page.waitForTimeout(15000);
    await page.getByRole('button', { name: 'Close documents' }).click();
    await page.getByRole('button', { name: 'Documents' }).click();
    await page.getByText('Local workbench disconnected. Start SovereignAI, then retry the connection.').waitFor({ timeout: 10000 });
    const retry = page.getByRole('button', { name: 'Retry connection' });
    if (!(await retry.isVisible())) throw new Error('Retry action is missing');
    await retry.click();
    await page.getByText('Local workbench disconnected. Start SovereignAI, then retry the connection.').waitFor();
    console.log('disconnected_state_and_retry_passed');
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
