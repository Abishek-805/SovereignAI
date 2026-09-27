const { chromium } = require('playwright');
const path = require('node:path');

(async () => {
 const base = 'http://127.0.0.1:8088';
 const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
 const page = await browser.newPage({ viewport: { width: 1600, height: 900 }, colorScheme: 'dark' });
 page.setDefaultTimeout(20000);
 const errors = [];
 page.on('pageerror', error => errors.push(String(error)));
 let id, names = [];
 try {
  const listed = await (await page.request.get(`${base}/coding/workspaces`)).json();
  if (!listed.length) throw Error('No workspace available for Explorer acceptance');
  id = listed[0].workspace_id;
  const suffix = Date.now().toString(36);
  const source = `context-${suffix}.txt`;
  const copied = `context-${suffix} copy.txt`;
  const renamed = `context-${suffix}-renamed.txt`;
  const folder = `context-${suffix}-folder`;
  const holder = `${folder}/holder.txt`;
  const moved = `${folder}/${source}`;
  names = [source, copied, renamed, holder, moved];
  for (const [name, content] of [[source, 'Explorer file actions'], [holder, 'holder']]) {
   const response = await page.request.put(`${base}/coding/workspaces/${id}/files/${encodeURIComponent(name)}`, { data: { content } });
   if (!response.ok()) throw Error(`Could not create ${name}: ${response.status()}`);
  }
  await page.goto(`${base}/#/`);
  await page.getByRole('navigation', { name: 'Primary workbench navigation' }).getByRole('button', { name: 'Code' }).click();
  const ide = page.getByRole('region', { name: 'Coding workspace' });
  await ide.getByLabel('Open coding workspace').selectOption(id);
  const tree = ide.getByLabel('Workspace files');
  const sourceButton = tree.getByRole('button', { name: source });
  await sourceButton.click({ button: 'right' });
  const menu = ide.getByRole('menu', { name: 'File actions' });
  await menu.waitFor();
  await page.screenshot({ path: path.resolve('../..', 'benchmarks/code-file-menu.png') });
  await ide.getByRole('button', { name: 'Search files', exact: true }).click();
  if (await menu.count()) throw Error('Context menu stayed open after outside click');
  await ide.getByRole('button', { name: 'Show Explorer' }).click();
  await sourceButton.click({ button: 'right' });
  await page.keyboard.press('Escape');
  if (await menu.count() || !await ide.isVisible()) throw Error('Escape did not close only the file menu');
  await sourceButton.focus();
  await page.keyboard.press('F2');
  await ide.getByRole('dialog', { name: 'Rename file' }).getByRole('button', { name: 'Cancel' }).click();
  await sourceButton.focus();
  await page.keyboard.press('Control+c');
  await sourceButton.click({ button: 'right' });
  await menu.getByRole('menuitem', { name: 'Paste' }).click();
  const copiedButton = tree.getByRole('button', { name: copied });
  await copiedButton.waitFor();
  await copiedButton.click({ button: 'right' });
  await menu.getByRole('menuitem', { name: 'Rename' }).click();
  await ide.getByRole('dialog', { name: 'Rename file' }).getByRole('textbox', { name: 'New file name' }).fill(renamed);
  await ide.getByRole('dialog', { name: 'Rename file' }).getByRole('button', { name: 'Rename' }).click();
  const renamedButton = tree.getByRole('button', { name: renamed });
  await renamedButton.waitFor();
  await ide.locator('.file-tabs').getByRole('button', { name: renamed, exact: true }).waitFor();
  await renamedButton.click({ button: 'right' });
  await menu.getByRole('menuitem', { name: 'Delete' }).click();
  await ide.getByRole('dialog', { name: 'Delete file' }).getByRole('button', { name: 'Delete' }).click();
  await renamedButton.waitFor({ state: 'detached' });
  await sourceButton.click({ button: 'right' });
  await menu.getByRole('menuitem', { name: 'Cut' }).click();
  await tree.getByText(folder).click({ button: 'right' });
  await menu.getByRole('menuitem', { name: 'Paste' }).click();
  let files = [];
  for (let attempt = 0; attempt < 30; attempt++) {
   files = (await (await page.request.get(`${base}/coding/workspaces/${id}`)).json()).files.map(file => file.name);
   if (files.includes(moved) && !files.includes(source)) break;
   await page.waitForTimeout(100);
  }
  if (!files.includes(moved) || files.includes(source)) throw Error('Cut and paste did not move file: '+JSON.stringify(files));
  if (errors.length) throw Error(errors.join('\n'));
  console.log('Explorer keyboard and context-menu file actions passed');
 } finally {
  if (id) for (const name of names) {
   await page.request.post(`${base}/coding/workspaces/${id}/file-operation`, { data: { action: 'delete', source: name } }).catch(() => undefined);
  }
  await browser.close();
 }
})().catch(error => { console.error(error); process.exitCode = 1; });
