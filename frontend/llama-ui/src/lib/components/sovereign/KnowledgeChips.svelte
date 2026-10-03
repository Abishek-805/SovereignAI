<script lang="ts">
	import X from '@lucide/svelte/icons/x';
	import FileText from '@lucide/svelte/icons/file-text';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import { KnowledgeService, type KnowledgeReference } from '$lib/services/knowledge.service';
	let { documents, onremove }: { documents: KnowledgeReference[]; onremove: (id: string) => void } =
		$props();
</script>

{#if documents.length}<div class="knowledge-context-chips" aria-label="Connected knowledge">
	<details><summary><ChevronRight size={14} /><span>{documents.length} connected documents</span></summary>
		<div class="document-list">{#each documents as doc}<div>
				<button
					type="button"
					title="Open in Knowledge"
					onclick={() => KnowledgeService.open(doc.id)}><FileText size={13} />{doc.name}</button
				><button
					type="button"
					aria-label={'Disconnect ' + doc.name}
					onclick={() => onremove(doc.id)}><X size={13} /></button
				>
		</div>{/each}</div></details>
	</div>{/if}

<style>
	details { width: 100%; }
	summary { display: flex; align-items: center; gap: 6px; cursor: pointer; list-style: none; }
	summary::-webkit-details-marker { display: none; }
	summary :global(svg) { transition: transform 120ms; }
	details[open] summary :global(svg) { transform: rotate(90deg); }
	.document-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
</style>
