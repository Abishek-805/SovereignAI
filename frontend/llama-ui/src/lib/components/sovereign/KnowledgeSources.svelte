<script lang="ts">
	import { KnowledgeService, type KnowledgeSource, type KnowledgeCoverage } from '$lib/services/knowledge.service';
	let { sources, coverage }: { sources: KnowledgeSource[]; coverage?: KnowledgeCoverage } = $props();
</script>

{#if sources.length}<details class="knowledge-sources source-group">
		<summary class="source-group-heading">Sources <span>{sources.length}</span></summary>
        {#if coverage}<details class="knowledge-coverage">
            <summary>Evidence coverage · {coverage.covered_documents} of {coverage.requested_documents} documents</summary>
            <p>{coverage.all_indexed_passages_included ? 'All indexed passages were included.' : 'This answer uses excerpts. Some indexed passages were omitted to fit the model context.'} Indexed text may exclude content that could not be extracted.</p>
            {#each coverage.documents as doc}<p>{doc.display_name}: {doc.included_passages} of {doc.indexed_passages} indexed passages{doc.included_passages === 0 ? ' · not represented' : ''}</p>{/each}
        </details>{/if}
		{#each sources as source}<details>
				<summary
					><b>{source.label}</b>
					{source.display_name}{source.page ? ` · p. ${source.page}` : ''}</summary
				>
				<p>{source.text}</p>
				{#if source.document_id}<button
						onclick={() => KnowledgeService.open(source.document_id!, source.page, source.chunk_id)}
						>Open in Knowledge →</button
					>{/if}<a
					href={'/sources/' + source.chunk_id + '/original'}
					target="_blank"
					rel="noreferrer">Original file ↗</a
				>
			</details>{/each}
	</details>{/if}

<style>
	.source-group { margin-block: 16px; }
	.source-group-heading { cursor: pointer; font-weight: 600; padding-block: 10px; }
	.source-group-heading > span { color: var(--muted-foreground); font-size: 12px; margin-left: 6px; font-weight: 400; }
	.source-group > details { margin-left: 12px; }
</style>
