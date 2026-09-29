import { describe, it, expect } from 'vitest';
import { render } from 'vitest-browser-svelte';
import DuplicateAudit from '$lib/components/sovereign/DuplicateAudit.svelte';
describe('duplicate disclosure',()=>{
 it('starts collapsed, opens with a real list and treats names as text',async()=>{
  const view=render(DuplicateAudit,{groups:[{kept:{document_id:'a',display_name:'original.pdf'},removed:[{document_id:'b',display_name:'<script>copy.pdf</script>'}]}]});
  const details=document.querySelector('details.duplicate-audit') as HTMLDetailsElement;
  expect(details.open).toBe(false);
  await view.getByText('Removed files · 1').click();
  expect(details.open).toBe(true);
  expect(details.textContent).toContain('original.pdf');
  expect(details.querySelector('script')).toBeNull();
 });
});
