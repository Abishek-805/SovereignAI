<script lang="ts">
 let { isEmpty = false }: { isEmpty: boolean } = $props();
 function open(tab:string) { window.dispatchEvent(new CustomEvent('sovereign-open-workspace',{detail:{tab}})); }
</script>
<div class:hidden={!isEmpty} class="pointer-events-auto mx-auto mb-8 max-w-3xl px-5 text-center">
 <p class="mb-4 text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">SovereignAI · Your local workbench</p>
 <h1 class="mb-3 text-3xl font-semibold tracking-tight md:text-4xl">What are we working on?</h1>
 <p class="text-muted-foreground">Ask a question, work with your documents, or build something.</p>
 <div class="mt-7 grid grid-cols-2 gap-3 text-left md:grid-cols-4">
  {#each [['knowledge','Ask documents','Answers with sources'],['agent','Start an agent task','Plan, act and verify'],['code','Work on code','Edit, test and verify'],['runtime','Control Center','Models and local services']] as [tab,title,description]}
   <button class="rounded-xl border border-border p-4 transition-colors hover:bg-accent focus-visible:outline-2" onclick={() => open(tab)}><span class="block text-sm font-medium">{title}</span><span class="mt-1 block text-xs text-muted-foreground">{description}</span></button>
  {/each}
 </div>
</div>
