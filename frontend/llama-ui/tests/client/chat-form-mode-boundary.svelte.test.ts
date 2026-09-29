import ChatFormTestWrapper from './components/ChatFormTestWrapper.svelte';
import { SETTINGS_KEYS } from '$lib/constants';
import { settingsStore } from '$lib/stores/settings/index.svelte';
import { tick } from 'svelte';
import { expect, it, vi } from 'vitest';
import { userEvent } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';

it('keeps file creation requests in Chat even with a selected project', async () => {
 settingsStore.updateConfig(SETTINGS_KEYS.SEND_ON_ENTER, true);
 localStorage.setItem('sovereign-active-workspace','test-project');
 const onSubmit=vi.fn(), navigate=vi.fn();
 window.addEventListener('sovereign-open-workspace',navigate);
 try {
  const {container}=render(ChatFormTestWrapper,{onSubmit}); await tick();
  const input=container.querySelector('textarea')!;
  await userEvent.click(input); await userEvent.keyboard('can u create a txt file explaining abt nature');
  await userEvent.keyboard('{Enter}'); await tick();
  expect(onSubmit).toHaveBeenCalledTimes(1); expect(navigate).not.toHaveBeenCalled();
 } finally { window.removeEventListener('sovereign-open-workspace',navigate); localStorage.removeItem('sovereign-active-workspace'); }
});
