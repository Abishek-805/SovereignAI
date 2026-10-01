import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import TablePreview from '$lib/components/sovereign/TablePreview.svelte';

describe('worksheet live Find', () => {
 it('selects the first partial match while typing, navigates subsequent matches, and ignores stale results', async () => {
  const cells=['2','24','24A','24AB'];
  let releaseOld: (()=>void)|undefined;
  const pendingOld=new Promise<void>(resolve=>releaseOld=resolve);
  const fetchMock=vi.spyOn(globalThis,'fetch').mockImplementation(async input=>{
   const url=new URL(String(input),location.origin);
   if(url.pathname.endsWith('/find')) {
    const q=url.searchParams.get('q')||'';
    if(q==='2')await pendingOld;
    const matches=cells.flatMap((value,i)=>value.toLowerCase().includes(q.toLowerCase())?[{sheet:0,name:'Results',row:i+1,column:1,coordinate:`A${i+1}`,value}]:[]);
    return Response.json({matches,total:matches.length,offset:0});
   }
   return Response.json({sheets:[{name:'Results',row_count:4,column_count:1}],sheet:0,name:'Results',offset:0,total:4,rows:cells.map((value,i)=>({number:i+1,cells:[{coordinate:`A${i+1}`,value}]})),merges:[],widths:{}});
  });
  const screen=render(TablePreview,{documentId:'live-find'});
  try {
   await vi.waitFor(()=>expect(document.querySelector('[data-coordinate="A4"]')).not.toBeNull());
   const input=document.querySelector<HTMLInputElement>('[aria-label="Find cell values"]')!;
   const address=()=>document.querySelector<HTMLInputElement>('[aria-label="Cell address"]')!.value;
   const type=(text:string)=>{input.value=text;input.dispatchEvent(new Event('input',{bubbles:true}));};
   type('2');
   type('24');
   await vi.waitFor(()=>expect(address()).toBe('A2'));
   type('24a');
   await vi.waitFor(()=>expect(address()).toBe('A3'));
   releaseOld!();
   await vi.waitFor(()=>expect(document.querySelector('.sheet-find')?.textContent).toContain('1 of 2'));
   expect(address()).toBe('A3');
   const next=[...document.querySelectorAll<HTMLButtonElement>('.sheet-find button')].find(button=>button.textContent==='Next')!;
   await vi.waitFor(()=>expect(next.disabled).toBe(false));next.click();
   await vi.waitFor(()=>expect(address()).toBe('A4'));
   expect(document.querySelector('[data-coordinate="A4"]')?.closest('tr')?.classList.contains('selected-row')).toBe(true);
   type('2');
   await vi.waitFor(()=>expect(address()).toBe('A1'));
   type('');
   await vi.waitFor(()=>expect(next.disabled).toBe(true));
  } finally {releaseOld!();await screen.unmount();fetchMock.mockRestore();}
 });
});
