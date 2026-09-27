// Manual live-model smoke: the retained llama chat composer still sends ordinary chat.
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    await page.goto('http://127.0.0.1:8088/#/', { waitUntil: 'domcontentloaded' });
    const chat = page.getByRole('textbox', { name: 'Chat message' });
    await chat.fill('Reply with one short sentence about bubble sort.');
    const completion = page.waitForResponse((response) => response.url().endsWith('/v1/chat/completions') && response.request().method() === 'POST', { timeout: 90000 });
    await page.getByRole('button', { name: 'Send', exact: true }).click();
    const response = await completion;
    if (response.status() !== 200 || !(await response.text()).includes('data:')) throw new Error('Local chat stream failed');
    if (await page.locator('#sovereign-documents').count()) throw new Error('Ordinary chat opened an Agent task');
    console.log('Chat mode smoke passed: local streamed response, no Agent task view.');
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
