<script lang="ts">
 import { Bot, Code2, MessageSquare, SlidersHorizontal, Library } from '@lucide/svelte';
 import { uiStore, deviceStore } from '$lib/stores';
 import { onMount } from 'svelte';
 let active = $state('chat');
 onMount(() => {
  if (!deviceStore.isMobile && !localStorage.getItem('sovereign-navigation-v2')) {
   uiStore.isSidebarExpanded = true;
   localStorage.setItem('sovereign-navigation-v2','1');
  }
  const selected = (event: Event) => { active = (event as CustomEvent).detail?.tab || ''; };
  const closed = () => { active = 'chat'; };
  window.addEventListener('sovereign-open-workspace',selected);
  window.addEventListener('sovereign-workspace-selected',selected);
  window.addEventListener('sovereign-close-workspace',closed);
  return () => { window.removeEventListener('sovereign-open-workspace',selected); window.removeEventListener('sovereign-workspace-selected',selected); window.removeEventListener('sovereign-close-workspace',closed); };
 });
 let { expanded = true }: { expanded?: boolean } = $props();
 const items = [
  {tab:'chat', label:'Chat', icon:MessageSquare},
  {tab:'agent', label:'Agent', icon:Bot},
  {tab:'code', label:'Code', icon:Code2},
  {tab:'knowledge', label:'Knowledge', icon:Library},
  {tab:'runtime', label:'Control Center', icon:SlidersHorizontal}
 ];
 function open(tab:string) {
  if (deviceStore.isMobile) uiStore.isSidebarExpanded = false;
  if (tab === 'chat') { active = 'chat'; window.dispatchEvent(new Event('sovereign-close-workspace')); return; }
  window.dispatchEvent(new CustomEvent('sovereign-open-workspace',{detail:{tab}}));
 }
</script>
<nav class="mx-2 space-y-1 border-y border-border py-3" aria-label="Primary workbench navigation">
 {#if expanded}<p class="px-2 pb-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Workbench</p>{/if}
 {#each items as item}<button title={item.label} aria-label={item.label} aria-current={active === item.tab ? 'page' : undefined} class:bg-accent={active === item.tab} class="flex min-h-9 w-full items-center gap-3 rounded-lg px-2 py-2 text-left text-sm hover:bg-accent focus-visible:outline-2" onclick={() => open(item.tab)}><item.icon size={17}/>{#if expanded}<span>{item.label}</span>{/if}</button>{/each}
</nav>
