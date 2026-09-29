import { describe, expect, it, vi } from 'vitest';
import { bundleHtmlPreview } from '$lib/services/html-preview';
describe('HTML project preview',()=>{
 it('bundles local CSS and JS without literal closing-tag injection',async()=>{
  const read=vi.fn(async(path:string)=>path.endsWith('.css')?'body{color:green} /* </style><script>bad()</script> */':'window.greeting="Hello"; // </script>');
  const html=await bundleHtmlPreview('<link rel="stylesheet" href="styles.css"><script src="app.js"></script><p>Hello</p>','site/index.html',read);
  expect(read.mock.calls.map(call=>call[0])).toEqual(['site/styles.css','site/app.js']);
  const doc=new DOMParser().parseFromString(html,'text/html');
  expect(doc.querySelector('link')?.getAttribute('href')).toMatch(/^data:text\/css;base64,/);
  expect(doc.querySelectorAll('script')).toHaveLength(1);
  expect(doc.querySelector('script')?.getAttribute('src')).toMatch(/^data:text\/javascript;base64,/);
  expect(doc.querySelector('meta')?.getAttribute('content')).toContain("connect-src 'none'");
 });
 it('executes the bundled script and renders its stylesheet in an opaque sandbox',async()=>{
  const html=await bundleHtmlPreview('<link rel="stylesheet" href="styles.css"><p id="target">Hello</p><script src="app.js"></script>','index.html',async path=>path==='styles.css'?'#target{color:rgb(0,128,0)}':'parent.postMessage({previewProof:getComputedStyle(document.getElementById("target")).color},"*")');
  const iframe=document.createElement('iframe');iframe.setAttribute('sandbox','allow-scripts');
  const proof=new Promise<string>((resolve,reject)=>{
   const timer=setTimeout(()=>{window.removeEventListener('message',listener);reject(new Error('Preview did not execute'));},5000);
   function listener(event:MessageEvent){if(event.source===iframe.contentWindow&&event.data?.previewProof){clearTimeout(timer);window.removeEventListener('message',listener);resolve(event.data.previewProof);}}
   window.addEventListener('message',listener);
  });
  iframe.srcdoc=html;document.body.append(iframe);
  try{expect(await proof).toBe('rgb(0, 128, 0)');}finally{iframe.remove();}
 });
 it('does not fetch outside the project and respects asset count and size budgets',async()=>{
  const read=vi.fn(async()=> 'x'.repeat(256*1024+1));
  const html=await bundleHtmlPreview('<base href="https://example.com"><script src="https://example.com/x.js"></script>'+Array.from({length:20},(_,i)=>`<script src="${i}.js"></script>`).join(''),'index.html',read);
  expect(read.mock.calls.length).toBe(15);
  expect(html).not.toContain('data:text/javascript');
  expect(new DOMParser().parseFromString(html,'text/html').querySelector('base')).toBeNull();
 });
});
