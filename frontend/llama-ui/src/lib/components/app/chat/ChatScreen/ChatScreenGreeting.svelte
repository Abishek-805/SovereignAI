<script lang="ts">
	import Files from '@lucide/svelte/icons/files';
	import Bot from '@lucide/svelte/icons/bot';
	import Code2 from '@lucide/svelte/icons/code-2';
	import { knowledgeContext } from '$lib/stores/knowledge-context.svelte';
	let { isEmpty = false }: { isEmpty: boolean } = $props();
	function open(tab: string) {
		if (tab === 'knowledge') {
			knowledgeContext.pickerOpen = true;
			return;
		}
		window.dispatchEvent(new CustomEvent('sovereign-open-workspace', { detail: { tab } }));
	}
</script>

<div class:hidden={!isEmpty} class="chat-welcome pointer-events-auto">
	<h1>Ask anything. Start here.</h1>
	<p>A private conversation, with your documents and local tools when you need them.</p>
	<div class="chat-entry-actions" aria-label="Start with context or a workspace">
		<button onclick={() => open('knowledge')}><Files size={16} />Connect knowledge</button>
		<button onclick={() => open('agent')}><Bot size={16} />Start a task</button>
		<button onclick={() => open('code')}><Code2 size={16} />Open code</button>
	</div>
</div>

<style>
	.chat-welcome {
		width: min(860px, 100%);
		margin: 0 auto 24px;
		padding: 0 20px;
		color: var(--foreground);
	}
	h1 {
		font-size: clamp(25px, 3vw, 32px);
		font-weight: 600;
		letter-spacing: -0.03em;
		line-height: 1.3;
		margin-bottom: 12px;
	}
	p {
		max-width: 610px;
		font-size: 14px;
		line-height: 1.75;
		color: var(--muted-foreground);
	}
	.chat-entry-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		margin-top: 22px;
	}
	button {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		border: 1px solid var(--border);
		border-radius: 7px;
		padding: 9px 12px;
		font-size: 12px;
		white-space: nowrap;
	}
	button :global(svg) {
		color: var(--muted-foreground);
	}
	button:hover {
		background: var(--wb-raised);
	}
	button:focus-visible {
		outline: 2px solid var(--wb-focus);
		outline-offset: 3px;
	}
	@media (max-width: 600px) {
		.chat-welcome {
			padding: 0 8px;
			margin-bottom: 20px;
		}
		.chat-entry-actions {
			gap: 6px;
		}
		button {
			font-size: 11px;
			padding: 8px 9px;
		}
	}
</style>
