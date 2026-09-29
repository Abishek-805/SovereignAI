<script lang="ts">
 import type { DuplicateGroup } from '$lib/services/duplicate-audit';
 let { groups = [] }: { groups?: DuplicateGroup[] } = $props();
</script>
{#if groups.length}
 <details class="duplicate-audit">
  <summary>Removed files · {groups.reduce((count, group) => count + group.removed.length, 0)}</summary>
  {#each groups as group}
   <div class="duplicate-group"><p>Kept: <strong>{group.kept.display_name}</strong></p>
    <ul>{#each group.removed as item}<li><span>Removed:</span> {item.display_name}</li>{/each}</ul>
   </div>
  {/each}
  <p class="preserved">Original source files were preserved.</p>
 </details>
{/if}
<style>
 .duplicate-audit { margin: .75rem 0; color: var(--foreground); font-size: .85rem; }
 summary { cursor: pointer; padding: .5rem 0; }
 summary:focus-visible { outline: 2px solid #9ed5c8; outline-offset: 3px; }
 .duplicate-group { margin: .5rem 0; padding: .5rem .75rem; border-left: 1px solid var(--border); overflow-wrap: anywhere; }
 p { margin: .25rem 0; } ul { margin: .5rem 0; padding-left: 1.2rem; } li { margin: .35rem 0; }
 li span, .preserved { color: var(--muted-foreground); }
</style>
