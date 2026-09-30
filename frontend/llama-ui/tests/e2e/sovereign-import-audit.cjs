const { chromium } = require('playwright');
(async () => {
 const browser=await chromium.launch({headless:true, executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  page.setDefaultTimeout(20000);
  const identity=await page.request.get('http://127.0.0.1:8088/status');
  if(identity.headers()['x-sovereign-audit']!=='disposable') throw Error('Refusing to test against a non-disposable backend');
  await page.goto('http://127.0.0.1:8088');
  await page.getByRole('navigation',{name:'Primary workbench navigation'}).getByRole('button',{name:'Knowledge',exact:true}).click();
  const library=page.getByRole('region',{name:'Knowledge library'});
  await library.waitFor();
  await library.locator('input[type=file]').first().setInputFiles({name:'browser-notes.tsv',mimeType:'text/tab-separated-values',buffer:Buffer.from('Name\tValue\nEarth\t42')});
  await library.getByRole('button',{name:'Stop import',exact:true}).waitFor();
  await library.getByText('1 document indexed.',{exact:true}).waitFor();
  if(!(await page.request.get('http://127.0.0.1:8088/documents')).ok()) throw Error('Library request failed');
  await library.locator('input[type=file]').first().setInputFiles({name:'cancel-browser.txt',mimeType:'text/plain',buffer:Buffer.from('Another passage about Earth.\n'.repeat(800))});
  await library.getByRole('button',{name:'Stop import',exact:true}).click();
  await library.getByText(/stopped before/).waitFor();
  const documents=await (await page.request.get('http://127.0.0.1:8088/documents')).json();
  if(documents.length!==1 || documents[0].display_name!=='browser-notes.tsv') throw Error('Cancelled import was published');
  await library.locator('input[type=file]').first().setInputFiles({name:'browser-large.tsv',mimeType:'text/tab-separated-values',buffer:Buffer.from('name\tvalue\n'+Array.from({length:120},(_,i)=>`Record-${i}\t${i}`).join('\n'))});
  await library.getByText('1 document indexed.',{exact:true}).waitFor();
  await library.getByRole('button',{name:/browser-large.tsv/}).click();
  const pagination=library.getByRole('navigation',{name:'Document passages'});
  await pagination.getByRole('button',{name:'Next passages'}).click();
  await pagination.getByText('Passages 101–121 of 121',{exact:true}).waitFor();
  if(await library.locator('[id^="passage-"]').count()!==21) throw Error('Large preview did not paginate');
  await pagination.getByRole('button',{name:'Previous passages'}).click();
  await pagination.getByText('Passages 1–100 of 121',{exact:true}).waitFor();
  await page.request.post('http://127.0.0.1:8088/__audit_shutdown__');
  console.log('Browser import, progress, cancellation, publication and large-preview pagination passed on disposable data.');
 } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
