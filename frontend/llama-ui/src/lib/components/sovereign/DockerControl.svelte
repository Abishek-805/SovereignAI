<script lang="ts">
 import { onDestroy } from 'svelte';
 import { WorkbenchService } from '$lib/services/workbench.service';
 let { onready = () => {} }: { onready?: () => void } = $props();
 let starting = $state(false);
 let notice = $state('');
 let disposed = false;
 onDestroy(() => { disposed = true; });
 async function start() {
  starting = true;
  notice = 'Starting Docker Desktop…';
  try {
   const response = await fetch('/workbench/docker/start', { method: 'POST' });
   const result = await response.json();
   if (!response.ok) throw new Error(result.message || 'Docker could not start');
   for (let attempt = 0; attempt < 18 && !disposed; attempt++) {
    const info = await WorkbenchService.info();
    if (info.sandbox.ready) { notice = 'Docker is ready. You can run code now.'; onready(); return; }
    notice = `Checking Docker… ${info.sandbox.reason || ''}`;
    const verification = await fetch('/workbench/docker/verify', { method: 'POST' });
    if (verification.ok) {
     let check = await verification.json();
     while (check.state === 'running' && !disposed) {
      notice = check.stage || 'Verifying sandbox isolation…';
      await new Promise(resolve => setTimeout(resolve, 1000));
      const progress = await fetch(`/coding/jobs/${encodeURIComponent(check.job_id)}`);
      if (!progress.ok) throw new Error('Cannot read sandbox verification progress');
      check = await progress.json();
     }
     if (check.state === 'completed') {
      const refreshed = await WorkbenchService.info();
      if (refreshed.sandbox.ready) { notice = 'Docker is ready. You can run code now.'; onready(); return; }
     }
     if (check.error) {
      if (check.error_code !== 'sandbox_unavailable') throw new Error(check.error);
      notice = check.error;
     }
    }
    await new Promise(resolve => setTimeout(resolve, 5000));
   }
   if (!disposed) notice = `Docker setup is incomplete. ${notice} No project code was run.`;
  } catch (error) { notice = `${error instanceof Error ? error.message : String(error)} No project code was run.`; }
  finally { starting = false; }
 }
</script>
<div class="mt-3 space-y-2">
 <button class="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50" disabled={starting} onclick={start}>{starting ? 'Starting Docker…' : 'Start Docker'}</button>
 {#if notice}<p class="text-sm text-muted-foreground" role="status">{notice}</p>{/if}
</div>
