<script lang="ts">
	import Bot from '@lucide/svelte/icons/bot';
	import Code2 from '@lucide/svelte/icons/code-2';
	import MessageSquare from '@lucide/svelte/icons/message-square';
	import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal';
	import Library from '@lucide/svelte/icons/library';
	import { uiStore, deviceStore } from '$lib/stores';
	import { onMount } from 'svelte';
	let active = $state('chat');
	onMount(() => {
		if (window.innerWidth >= 1024) uiStore.isSidebarExpanded = localStorage.getItem('sovereign-navigation-expanded') !== 'false';
		const selected = (event: Event) => {
			active = (event as CustomEvent).detail?.tab || '';
		};
		const closed = () => {
			active = 'chat';
		};
		window.addEventListener('sovereign-open-workspace', selected);
		window.addEventListener('sovereign-workspace-selected', selected);
		window.addEventListener('sovereign-close-workspace', closed);
		return () => {
			window.removeEventListener('sovereign-open-workspace', selected);
			window.removeEventListener('sovereign-workspace-selected', selected);
			window.removeEventListener('sovereign-close-workspace', closed);
		};
	});
	let { expanded = true }: { expanded?: boolean } = $props();
	const items = [
		{ tab: 'chat', label: 'Chat', icon: MessageSquare },
		{ tab: 'agent', label: 'Agent', icon: Bot },
		{ tab: 'code', label: 'Code', icon: Code2 },
		{ tab: 'knowledge', label: 'Knowledge', icon: Library },
		{ tab: 'runtime', label: 'Control Center', icon: SlidersHorizontal }
	];
	function open(tab: string) {
		if (deviceStore.isMobile) uiStore.isSidebarExpanded = false;
		if (tab === 'chat') {
			active = 'chat';
			window.dispatchEvent(new Event('sovereign-close-workspace'));
			return;
		}
		window.dispatchEvent(new CustomEvent('sovereign-open-workspace', { detail: { tab } }));
	}
</script>

<nav
	class="workbench-navigation"
	class:collapsed={!expanded}
	aria-label="Primary workbench navigation"
>
	{#each items as item}
		{#if item.tab === 'runtime'}<div class="navigation-divider" aria-hidden="true"></div>{/if}
		<button
			title={item.label}
			aria-label={item.label}
			aria-current={active === item.tab ? 'page' : undefined}
			class:active={active === item.tab}
			onclick={() => open(item.tab)}
		>
			<item.icon size={17} strokeWidth={1.7} />
			{#if expanded}<span>{item.label}</span>{/if}
		</button>
	{/each}
</nav>

<style>
	.workbench-navigation {
		display: grid;
		gap: 4px;
		margin: 0 6px;
		padding: 8px 0 14px;
	}
	button {
		display: flex;
		align-items: center;
		gap: 12px;
		min-height: 40px;
		width: 100%;
		padding: 9px 11px;
		text-align: left;
		border: 1px solid transparent;
		border-radius: 7px;
		color: var(--muted-foreground);
		font-size: 13px;
	}
	button:hover {
		background: var(--wb-raised);
		color: var(--foreground);
	}
	button.active {
		background: var(--wb-raised);
		border-color: var(--border);
		color: var(--foreground);
		font-weight: 550;
	}
	button:focus-visible {
		outline: 2px solid var(--wb-focus);
		outline-offset: 2px;
	}
	button :global(svg) {
		flex: none;
	}
	.navigation-divider {
		height: 1px;
		background: var(--border);
		margin: 10px 6px 5px;
	}
	.collapsed {
		margin-inline: 0;
	}
	.collapsed button {
		justify-content: center;
		padding-inline: 6px;
	}
</style>
