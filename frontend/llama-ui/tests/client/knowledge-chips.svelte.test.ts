import { expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import KnowledgeChips from '$lib/components/sovereign/KnowledgeChips.svelte';

it('keeps connected documents collapsed and allows disconnect after expanding', async () => {
 const onremove = vi.fn();
 const { container } = render(KnowledgeChips, { documents: [{ id: 'one', name: 'scores.xlsx' }], onremove });
 const summary = container.querySelector('summary')!;
 const remove = container.querySelector<HTMLButtonElement>('[aria-label="Disconnect scores.xlsx"]')!;
 expect(remove.checkVisibility()).toBe(false);
 summary.click();
 await vi.waitFor(() => expect(remove.checkVisibility()).toBe(true));
 remove.click();
 expect(onremove).toHaveBeenCalledWith('one');
 summary.click();
 await vi.waitFor(() => expect(remove.checkVisibility()).toBe(false));
});

