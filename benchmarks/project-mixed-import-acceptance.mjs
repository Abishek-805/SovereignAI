// Real production import controls/API; mutations confined to one suite-owned project.
import { chromium } from '../frontend/llama-ui/node_modules/playwright/index.mjs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
const base = 'http://127.0.0.1:8088', out = 'benchmarks/project-mixed-import-acceptance/';
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true });
const checks = [], errors = [];
const ensure = (value, message) => { if (!value) throw Error(message); };
const api = async (path, body) => { const r = await fetch(base + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); ensure(r.ok, await r.clone().text()); return r.json(); };
try {
 const workspace = await api('/coding/workspaces', { name: 'Mixed import acceptance ' + Date.now() });
 const context = await browser.newContext({ viewport: { width: 1600, height: 900 }, serviceWorkers: 'block' });
 const page = await context.newPage(); page.on('pageerror', error => errors.push(String(error)));
 await page.goto(base);
 await page.getByRole('navigation', { name: 'Primary workbench navigation' }).getByRole('button', { name: 'Code', exact: true }).click();
 await page.getByLabel('Open coding workspace').selectOption(workspace.workspace_id);
 const image = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK2cAAAAASUVORK5CYII=', 'base64');
 const files = [
  { name: 'photo.png', mimeType: 'image/png', buffer: Buffer.concat([image, Buffer.alloc(150000)]) },
  { name: 'manual.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.7\n\0binary\xff', 'latin1') },
  { name: 'main.ts', mimeType: 'text/plain', buffer: Buffer.from('export const value = 42;\r\n') },
  { name: 'shape.svg', mimeType: 'image/svg+xml', buffer: Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"/>') }
 ];
 const chooser = page.waitForEvent('filechooser'); await page.getByLabel('Import files', { exact: true }).click();
 await (await chooser).setFiles(files);
 await page.locator('.ide footer').filter({ hasText: 'Imported 4 files. 0 skipped.' }).waitFor();
 for (const file of files) ensure((await readFile(join(workspace.host_path, file.name))).equals(file.buffer), 'Host bytes changed: ' + file.name);
 checks.push({ test: 'Import button opens picker; simultaneous PNG >128 KB, PDF, TypeScript and SVG preserve host bytes', passed: true });
 // File rows expose the relative path as title; avoid matching editor tabs.
 await page.locator('.explorer [title="photo.png"]').last().dblclick();
 const preview = page.locator('.asset-preview img'); await preview.waitFor();
 await page.waitForFunction(() => { const img = document.querySelector('.asset-preview img'); return img?.complete && img.naturalWidth > 0; });
 await page.locator('.asset-preview a[download]').waitFor();
 checks.push({ test: 'Imported image renders safely and offers original download', passed: true });
 const raw = await page.request.get(base + '/coding/workspaces/' + workspace.workspace_id + '/assets/manual.pdf');
 ensure(raw.ok() && (await raw.body()).equals(files[1].buffer), 'Binary download changed');
 await page.locator('.ide [data-import="files"]').setInputFiles([files[0]]);
 await page.locator('.ide footer').filter({ hasText: 'Imported 0 files. 1 skipped.' }).waitFor();
 // Frontend detects existing paths before upload, so verify collision through the real API too.
 const collision = await page.request.post(base + '/coding/workspaces/' + workspace.workspace_id + '/import-files/photo.png', { data: Buffer.from('replacement'), headers: { 'Content-Type': 'application/octet-stream' } });
 ensure(collision.status() === 409, 'Duplicate import overwrote existing file');
 ensure((await readFile(join(workspace.host_path, 'photo.png'))).equals(files[0].buffer), 'Collision changed image');
 checks.push({ test: 'Binary download and collision refusal preserve originals', passed: true });
 await page.screenshot({ path: out + 'mixed-assets.png' });
 const folderPath = resolve(out, 'folder-fixture');
 await mkdir(join(folderPath, 'assets'), { recursive: true });
 await writeFile(join(folderPath, 'assets', 'pixel.png'), image);
 await writeFile(join(folderPath, 'index.js'), 'export const imported = true;\n');
 const folderChooser = page.waitForEvent('filechooser'); await page.getByLabel('Import folder', { exact: true }).click();
 await (await folderChooser).setFiles(folderPath);
 await page.locator('.ide footer').filter({ hasText: 'Imported 2 files. 0 skipped.' }).waitFor();
 const folderId = await page.getByLabel('Open coding workspace').inputValue();
 const folderWorkspace = await (await page.request.get(base + '/coding/workspaces/' + folderId)).json();
 ensure(folderId !== workspace.workspace_id && (await readFile(join(folderWorkspace.host_path, 'assets', 'pixel.png'))).equals(image), 'Folder import lost relative paths or binary bytes');
 checks.push({ test: 'Folder picker imports nested mixed files into a host project with exact relative paths', passed: true, workspace_id: folderId, host_path: folderWorkspace.host_path });
 // Monaco may cancel background editor work on disposal; any other page error fails.
 ensure(errors.filter(error => !/Canceled/.test(error)).length === 0, errors.join('\n'));
 await writeFile(out + 'results.json', JSON.stringify({ workspace_id: workspace.workspace_id, host_path: workspace.host_path, checks, errors }, null, 2));
 console.log(JSON.stringify({ passed: checks.length, errors, workspace_id: workspace.workspace_id }));
} finally { await browser.close(); }
