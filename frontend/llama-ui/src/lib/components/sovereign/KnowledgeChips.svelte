<script lang="ts">
	import X from '@lucide/svelte/icons/x';
	import FileText from '@lucide/svelte/icons/file-text';
	import { KnowledgeService, type KnowledgeReference } from '$lib/services/knowledge.service';
	let { documents, onremove }: { documents: KnowledgeReference[]; onremove: (id: string) => void } =
		$props();
</script>

{#if documents.length}<div class="knowledge-context-chips" aria-label="Connected knowledge">
		<span>Knowledge</span>{#each documents as doc}<div>
				<button
					type="button"
					title="Open in Knowledge"
					onclick={() => KnowledgeService.open(doc.id)}><FileText size={13} />{doc.name}</button
				><button
					type="button"
					aria-label={'Disconnect ' + doc.name}
					onclick={() => onremove(doc.id)}><X size={13} /></button
				>
			</div>{/each}
	</div>{/if}
