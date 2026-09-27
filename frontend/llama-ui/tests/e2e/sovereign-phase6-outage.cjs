// Manual smoke: stop the isolated workbench after ready_for_disconnect,
// then restart it after ready_for_restore. The local model stays running.
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  try {
    await page.goto('http://127.0.0.1:8088/#/', { waitUntil: 'commit' });
    await page.getByRole('button', { name: 'Documents' }).click();
    await page.getByText('Indexed documents (2)').waitFor();
    console.log('ready_for_disconnect');
    await page.waitForTimeout(30000);
    await page.getByRole('button', { name: 'Close documents' }).click();
    await page.getByRole('button', { name: 'Documents' }).click();
    await page.getByText('Local workbench disconnected. Start SovereignAI, then retry the connection.').waitFor({ timeout: 12000 });
    await page.getByRole('button', { name: 'Retry connection' }).click();
    await page.getByText('Local workbench disconnected. Start SovereignAI, then retry the connection.').waitFor();
    console.log('disconnected_and_retry_passed ready_for_restore');
    await page.waitForTimeout(30000);
    await page.getByRole('button', { name: 'Retry connection' }).click();
    await page.getByText('Indexed documents (2)').waitFor({ timeout: 12000 });
    console.log('backend_recovery_passed');
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
