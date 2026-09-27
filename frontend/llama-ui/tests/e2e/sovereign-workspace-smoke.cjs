// Manual live browser smoke: real model edit, Docker tests, diff and result download.
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
  try {
    await page.goto('http://127.0.0.1:8088/#/', { waitUntil: 'commit' });
    await page.getByRole('navigation', { name: 'Primary workbench navigation' }).getByRole('button', { name: 'Code workspace', exact: true }).click();
    await page.getByLabel('New workspace name').fill('Phase 1 coding smoke');
    await page.getByRole('button', { name: 'Create workspace' }).click();
    await page.getByText('Workspace created.').waitFor();
    await page.getByLabel('File', { exact: true }).fill('solution.py');
    await page.getByLabel('Source').fill('def add(a, b):\n    return 0\n');
    await page.getByRole('button', { name: 'Save file' }).click();
    await page.getByText('Saved solution.py.').waitFor();
    await page.getByLabel('File', { exact: true }).fill('test_solution.py');
    await page.getByLabel('Source').fill(
      'import unittest\nfrom pathlib import Path\nfrom solution import add\n\n' +
      'class AddTest(unittest.TestCase):\n' +
      '    def test_add(self):\n' +
      '        self.assertEqual(add(2, 3), 5)\n' +
      "        Path('/output/result.txt').write_text(str(add(2, 3)))\n"
    );
    await page.getByRole('button', { name: 'Save file' }).click();
    await page.getByText('Saved test_solution.py.').waitFor();
    await page.getByRole('button', { name: /solution.py.*B/ }).first().click();
    await page.getByLabel('Coding task').fill('Fix add so it returns the sum of its arguments. Keep the same function signature.');
    await page.getByRole('button', { name: 'Run in Docker' }).click();
    await page.getByText(/Verified after \d+ attempt/).waitFor({ timeout: 180000 });
    const result = await page.getByLabel('Coding results').innerText();
    if (!result.includes('tests_passed: passed') || !result.includes('result.txt')) throw new Error(result.slice(0, 800));
    if (!(await page.getByLabel('Source').inputValue()).includes('return a + b')) throw new Error('Verified edit was not loaded');
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('link', { name: 'result.txt (1 B)' }).click()
    ]);
    const file = await download.path();
    const content = require('node:fs').readFileSync(file, 'utf8');
    if (content !== '5') throw new Error('Artifact was not the container result');
    await download.delete();
    console.log(JSON.stringify({ status: 'passed', artifact: content, result: result.slice(0, 600) }));
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
