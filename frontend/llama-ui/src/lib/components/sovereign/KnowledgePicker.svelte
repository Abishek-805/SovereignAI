<script lang="ts">
	import * as Dialog from '$lib/components/ui/dialog';
	import Search from '@lucide/svelte/icons/search';
	import FileText from '@lucide/svelte/icons/file-text';
	import {
		KnowledgeService,
		type KnowledgeReference,
		type KnowledgeDocument
	} from '$lib/services/knowledge.service';
	let {
		open = $bindable(false),
		selected = [],
		scope = 'all',
		onconnect
	}: {
		open?: boolean;
		selected?: KnowledgeReference[];
		scope?: 'all' | 'selected';
		onconnect: (docs: KnowledgeReference[], scope: 'all' | 'selected') => void;
	} = $props();
	let docs = $state<KnowledgeDocument[]>([]),
		chosen = $state<string[]>([]),
		filter = $state(''),
		error = $state(''),
		loading = $state(false),
		all = $state(true);
	const visible = $derived(
		docs.filter((doc) => doc.display_name.toLowerCase().includes(filter.toLowerCase()))
	);
	$effect(() => {
		if (open) {
			chosen = selected.map((doc) => doc.id);
			all = scope === 'all';
			filter = '';
			void refresh();
		}
	});
	async function refresh() {
		loading = true;
		error = '';
		try {
			docs = await KnowledgeService.list();
		} catch (e) {
			error = String(e);
		} finally {
			loading = false;
		}
	}
	function toggle(id: string) {
		if (all) {
			chosen = docs.map((doc) => doc.document_id);
			all = false;
		}
		chosen = chosen.includes(id)
			? chosen.filter((item) => item !== id)
			: chosen.length < 256
				? [...chosen, id]
				: chosen;
	}
</script>

<Dialog.Root bind:open
	><Dialog.Content class="knowledge-picker sm:max-w-xl"
		><Dialog.Header
			><Dialog.Title>Connect Knowledge</Dialog.Title><Dialog.Description
				>Choose documents this conversation can read. Originals stay in your library.</Dialog.Description
			></Dialog.Header
		>
		<div class="context-search">
			<Search size={16} /><input
				aria-label="Search Knowledge"
				placeholder="Search documents…"
				bind:value={filter}
			/>
		</div>
		<label class="knowledge-all"
			><input
				type="checkbox"
				checked={all}
				onchange={(event) => {
					all = event.currentTarget.checked;
					if (!all) chosen = [];
				}}
			/>All documents in Knowledge <small>Includes new documents automatically.</small></label
		>
		<div class="context-picker-list">
			{#if loading}<p role="status">Reading your library…</p>{:else if error}<p role="alert">
					{error}
				</p>
				<button onclick={refresh}>Retry</button>{:else}{#each visible as doc}<label
						><input
							type="checkbox"
							checked={all || chosen.includes(doc.document_id)}
							onchange={() => toggle(doc.document_id)}
						/><FileText size={17} /><span
							><strong>{doc.display_name}</strong><small>{doc.chunk_count} indexed passages</small
							></span
						></label
					>{/each}{#if !visible.length}<p>
						{docs.length ? 'No matching documents.' : 'No documents yet. Add files in Knowledge.'}
					</p>{/if}{/if}
		</div>
		<Dialog.Footer
			><span class="context-picker-count"
				>{all ? 'Whole library' : chosen.length + ' selected'} · read access</span
			><button class="context-secondary" onclick={() => (open = false)}>Cancel</button><button
				class="context-primary"
				disabled={loading || !!error}
				onclick={() => {
					onconnect(
						docs
							.filter((doc) => all || chosen.includes(doc.document_id))
							.map((doc) => ({ id: doc.document_id, name: doc.display_name })),
						all ? 'all' : 'selected'
					);
					open = false;
				}}>Connect</button
			></Dialog.Footer
		>
	</Dialog.Content></Dialog.Root
>
