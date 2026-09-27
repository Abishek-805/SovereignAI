// Manual live acceptance run against a disposable SovereignAI data directory.
// Start the real model on 8087 and the workbench with SOVEREIGN_DATA_DIR on 8088.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const base = 'http://127.0.0.1:8088';
const evidence = path.resolve(__dirname, '../../../../benchmarks/phase6-acceptance');
fs.mkdirSync(evidence, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    acceptDownloads: true,
    permissions: ['clipboard-read', 'clipboard-write']
  });
  const page = await context.newPage();
  const findings = {};
  try {
    await page.goto(base + '/#/', { waitUntil: 'commit' });
    await page.getByRole('button', { name: 'Documents' }).waitFor({ timeout: 30000 });
    await page.getByRole('button', { name: 'Documents' }).click();
    await page.getByText('Import a document to begin.').waitFor();
    findings.empty = true;

    const fileInput = page.locator('#sovereign-documents input[type=file][accept*=".pdf"]');
    await fileInput.setInputFiles({ name: 'phase6-report.txt', mimeType: 'text/plain', buffer: Buffer.from('SYNTHETIC TEST DATA. Pump P-101 vibration measured 8.2 mm/s. Inspection recommends review against SOP-A.\n') });
    await page.getByText('Indexed documents (1)').waitFor({ timeout: 30000 });
    await fileInput.setInputFiles({ name: 'phase6-sop.txt', mimeType: 'text/plain', buffer: Buffer.from('SYNTHETIC TEST DATA. SOP-A requires investigation of Pump P-101 vibration above 7.1 mm/s. Do not shut down without approval.\n') });
    await page.getByText('Indexed documents (2)').waitFor({ timeout: 30000 });
    findings.import = true;

    await page.getByLabel('Ask with citations').fill('What was P-101 vibration, and what does SOP-A require? Cite the source passages.');
    let askRequests = 0;
    page.on('request', (request) => { if (request.url() === base + '/ask') askRequests++; });
    await page.getByRole('button', { name: 'Ask documents' }).click();
    findings.concurrentDisabled = await page.getByRole('button', { name: 'Ask documents' }).isDisabled();
    await page.getByRole('status').filter({ hasText: /Answer linked|selected documents do not|Citation check failed|Local model|Request failed/ }).waitFor({ timeout: 150000 });
    findings.askRequests = askRequests;
    findings.answerStatus = await page.getByRole('status').last().innerText();
    findings.answerText = (await page.getByLabel('Document answer').innerText()).slice(0, 350);

    await page.getByRole('button', { name: 'Deliverables' }).click();
    const checks = page.locator('#sovereign-documents input[type=checkbox]');
    await checks.nth(0).check(); await checks.nth(1).check();
    await page.getByRole('button', { name: 'Create maintenance draft' }).click();
    await page.getByRole('link', { name: 'Word draft' }).waitFor({ timeout: 60000 });
    findings.downloads = {};
    for (const [name, label] of [['word', 'Word draft'], ['excel', 'Excel calculations'], ['slides', 'Slide briefing']]) {
      const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('link', { name: label }).click()]);
      const target = path.join(evidence, 'phase6-' + download.suggestedFilename());
      await download.saveAs(target);
      const bytes = fs.readFileSync(target);
      if (bytes.length < 100 || bytes.subarray(0, 2).toString() !== 'PK') throw new Error(name + ' is not a valid nonempty Office package');
      findings.downloads[name] = { name: download.suggestedFilename(), bytes: bytes.length };
    }
    const aside = await page.getByLabel('Document workbench').boundingBox();
    findings.mobilePanelFits = aside && aside.x >= 0 && aside.x + aside.width <= 390;
    await page.screenshot({ path: path.join(evidence, 'mobile.png') });
    await page.setViewportSize({ width: 1440, height: 900 });
    const desktopAside = await page.getByLabel('Document workbench').boundingBox();
    findings.desktopPanelFits = desktopAside && desktopAside.x >= 0 && desktopAside.x + desktopAside.width <= 1440;
    await page.screenshot({ path: path.join(evidence, 'desktop.png') });
    console.log(JSON.stringify(findings, null, 2));
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
