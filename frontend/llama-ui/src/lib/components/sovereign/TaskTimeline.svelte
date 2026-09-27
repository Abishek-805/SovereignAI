<script lang="ts">
	type Event = {
		state?: string;
		event?: string;
		tool?: string;
		reason?: string;
		status?: string;
		attempt?: number;
		exit_code?: number;
		checks?: Record<string, boolean>;
	};
	let { events = [], title = 'Activity' }: { events?: Event[]; title?: string } = $props();
	function label(event: Event): string {
		return (event.tool || event.event || event.state || 'Check').replaceAll('_', ' ');
	}
	function failed(event: Event): boolean {
		return event.status === 'error' || event.state === 'failed' || event.event === 'test_failed' ||
			(event.exit_code !== undefined && event.exit_code !== 0) ||
			(event.checks !== undefined && Object.values(event.checks).some((passed) => !passed));
	}
</script>

<section aria-label={title} class="rounded-xl border border-border bg-card/70 p-3">
	<h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
	{#if events.length}
		<ol class="space-y-2 border-l border-border pl-3 text-sm">
			{#each events as event}
				<li class="relative break-words">
					<span class={'absolute -left-[19px] top-0 text-xs ' + (failed(event) ? 'text-destructive' : 'text-emerald-500')} aria-hidden="true">{failed(event) ? '×' : '•'}</span>
					<span class="capitalize">{label(event)}</span>
					{#if event.attempt}<span class="text-muted-foreground"> · attempt {event.attempt}</span>{/if}
					{#if event.exit_code !== undefined}<span class="text-muted-foreground"> · exit {event.exit_code}</span>{/if}
					{#if event.reason}<p class="text-xs text-muted-foreground">{event.reason}</p>{/if}
				</li>
			{/each}
		</ol>
	{:else}
		<p class="text-xs text-muted-foreground">No task events recorded yet.</p>
	{/if}
</section>
