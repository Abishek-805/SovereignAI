<script lang="ts">
	import './knowledge-workspace.css';
	import { onMount } from 'svelte';
	import { knowledgeContext } from '$lib/stores/knowledge-context.svelte';
	let { target = 'chat', onchoose, disabled = false }: { target?: 'chat' | 'agent'; onchoose?: () => void; disabled?: boolean } =
		$props();
	const connected = $derived(
		target === 'chat' ? knowledgeContext.connected : knowledgeContext.agentConnected
	);
	const scope = $derived(target === 'chat' ? knowledgeContext.scope : knowledgeContext.agentScope);
	const count = $derived(
		scope === 'all'
			? knowledgeContext.catalog.length
			: (target === 'chat' ? knowledgeContext.documents : knowledgeContext.agent).length
	);
	let error = $state('');
	async function toggle() {
		if (disabled) return;
		error = '';
		try {
			if (target === 'chat') await knowledgeContext.configure(!connected);
			else knowledgeContext.agentConnected = !connected;
		} catch (e) {
			error = String(e);
		}
	}
	onMount(() => {
		knowledgeContext.restorePending();
		void knowledgeContext.refresh().catch((e) => {
			error = String(e);
		});
	});
</script>

<div class="knowledge-connection">
	<button
		type="button"
		role="switch"
		aria-checked={connected}
		aria-label="Connect Knowledge"
		{disabled}
		title={disabled ? 'Knowledge scope is fixed for the running request. Change it before the next message.' : 'Connect or disconnect Knowledge'}
		onclick={toggle}
		><span class="knowledge-switch" class:enabled={connected}></span>Knowledge
		<span>{connected ? 'On' : 'Off'}</span></button
	>
	{#if connected}<button
			type="button"
			class="knowledge-scope"
			{disabled}
			onclick={() => (onchoose ? onchoose() : (knowledgeContext.pickerOpen = true))}
			>{scope === 'all' ? 'All documents' : count + ' selected'}
			<span>{scope === 'all' ? count + ' files' : 'Change'}</span></button
		>{/if}
	{#if error}<span role="alert">{error}</span>{/if}
</div>
