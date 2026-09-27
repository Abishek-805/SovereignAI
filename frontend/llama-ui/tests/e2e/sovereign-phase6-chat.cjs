// Manual live model acceptance: wake, longer answer, metrics, code-copy integrity.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    permissions: ['clipboard-read', 'clipboard-write']
  });
  const page = await context.newPage();
  const out = {};
  try {
    await page.addInitScript(() => {
      const original = navigator.clipboard.writeText.bind(navigator.clipboard);
      navigator.clipboard.writeText = async (text) => {
        window.__sovereignCopyInput = text;
        return original(text);
      };
    });
    const status = await context.request.get('http://127.0.0.1:8088/status');
    out.before = (await status.json()).generator;
    await page.goto('http://127.0.0.1:8088/#/', { waitUntil: 'commit' });
    const composer = page.getByRole('textbox', { name: 'Chat message' });
    await composer.waitFor({ timeout: 30000 });
    await composer.fill('Write eight numbered sentences explaining bubble sort in detail. Then include a fenced Python code block with exactly this function, preserving indentation and the literal comment characters: def bubble_sort(items):\\n    for i in range(len(items)):\\n        for j in range(len(items) - i - 1):\\n            if items[j] > items[j + 1]:\\n                items[j], items[j + 1] = items[j + 1], items[j]\\n    # <tag> & value\\n    return items');
    const completion = page.waitForResponse((response) => response.url().endsWith('/v1/chat/completions') && response.request().method() === 'POST', { timeout: 150000 });
    await page.getByRole('button', { name: 'Send', exact: true }).click();
    const response = await completion;
    const stream = await response.text();
    out.modelOutput = stream.split(/\r?\n/).filter((line) => line.startsWith('data: ')).map((line) => {
      try { return JSON.parse(line.slice(6)).choices?.[0]?.delta?.content || ''; } catch { return ''; }
    }).join('');
    await page.getByRole('button', { name: 'Copy code' }).waitFor({ timeout: 150000 });
    const code = page.locator('pre code').last();
    await code.waitFor();
    out.sourceText = await code.textContent();
    out.codeText = await code.innerText();
    await page.getByRole('button', { name: 'Copy code' }).last().click();
    out.clipboardInput = await page.evaluate(() => window.__sovereignCopyInput);
    out.clipboardText = await page.evaluate(() => navigator.clipboard.readText());
    out.copyExact = out.clipboardText === out.codeText;
    out.sourceInModelOutput = out.modelOutput.includes(out.sourceText.trimEnd());
    out.specialCharactersPreserved = out.sourceText.includes('# <tag> & value') && out.clipboardText.includes('# <tag> & value');
    out.sourcePassedExactly = out.clipboardInput === out.sourceText;
    out.copyContentEquivalent = out.clipboardText.replace(/\r\n/g, '\n') === out.sourceText.replace(/\r\n/g, '\n');
    out.newlines = {
      source: [...out.sourceText.matchAll(/\r\n|\n|\r/g)].map((match) => match[0] === '\r\n' ? 'CRLF' : match[0] === '\n' ? 'LF' : 'CR'),
      argument: [...out.clipboardInput.matchAll(/\r\n|\n|\r/g)].map((match) => match[0] === '\r\n' ? 'CRLF' : match[0] === '\n' ? 'LF' : 'CR'),
      clipboard: [...out.clipboardText.matchAll(/\r\n|\n|\r/g)].map((match) => match[0] === '\r\n' ? 'CRLF' : match[0] === '\n' ? 'LF' : 'CR')
    };
    out.codeIndent = out.clipboardText.includes('    for i in range');
    out.bodyScrollWidth = await page.locator('body').evaluate((el) => el.scrollWidth);
    out.answerLength = (await page.locator('body').innerText()).length;
    out.metrics = (await page.locator('body').innerText()).match(/\d+[\d,.]*\s*(tokens|t\/s|seconds|s)/gi)?.slice(-8) || [];
    out.after = (await (await context.request.get('http://127.0.0.1:8088/status')).json()).generator;
    const evidence = path.resolve(__dirname, '../../../../benchmarks/phase6-acceptance');
    fs.writeFileSync(path.join(evidence, 'chat-result.json'), JSON.stringify(out, null, 2));
    await page.screenshot({ path: path.join(evidence, 'chat-mobile.png') });
    console.log(JSON.stringify({ sourceInModelOutput: out.sourceInModelOutput, sourcePassedExactly: out.sourcePassedExactly, specialCharactersPreserved: out.specialCharactersPreserved, copyExact: out.copyExact, copyContentEquivalent: out.copyContentEquivalent, newlines: out.newlines, codeIndent: out.codeIndent }, null, 2));
    if (!out.sourceInModelOutput || !out.sourcePassedExactly || !out.specialCharactersPreserved || !out.copyContentEquivalent || !out.codeIndent) process.exitCode = 1;
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
