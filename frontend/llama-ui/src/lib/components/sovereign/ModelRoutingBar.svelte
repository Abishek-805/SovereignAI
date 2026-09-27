<script lang="ts">
 import { onMount } from 'svelte';
 import { ChevronDown, Cpu, RefreshCw } from '@lucide/svelte';
 import { WorkbenchService, type WorkbenchInfo } from '$lib/services/workbench.service';

 type Route = { task: string; capability: string; model: string; reason?: string };
 type Generator = WorkbenchInfo['runtime']['generator'];
 let info = $state<WorkbenchInfo | null>(null);
 let generator = $state<Generator | null>(null);
 let connected = $state(false);
 let initializing = $state(true);
 let open = $state(false);
 let refreshing = $state(false);
 let lastRoute = $state<Route | null>(null);
 let root: HTMLElement;

 const activeModel = $derived(info?.models.find(model => model.alias === generator?.alias));
 const runtimeState = $derived(!connected ? 'Disconnected' : !generator?.available ? 'Unavailable' : generator.is_sleeping ? 'Sleeping' : 'Loaded');
 const modelName = $derived(generator?.available ? activeModel?.model_id || generator?.alias || 'Local model' : 'No model running');

 async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try {
   const response = await fetch('/status', { cache: 'no-store' });
   if (!response.ok) throw new Error('Local backend unavailable');
   const status = await response.json();
   generator = status.generator;
   connected = true;
  } catch { connected = false; generator = null; }
  finally { refreshing = false; initializing = false; }
 }
 async function details() {
  try { info = await WorkbenchService.info(); generator = info.runtime.generator; connected = true; }
  catch { info = null; }
  finally { initializing = false; }
 }
 function toggle() { open = !open; if (open) void details(); }
 function dismiss(event: MouseEvent) { if (open && root && !root.contains(event.target as Node)) open = false; }
 onMount(() => {
  void refresh();
  void details();
  try { lastRoute = JSON.parse(sessionStorage.getItem('sovereign-last-route') || 'null'); } catch { /* Previous session data is optional. */ }
  const routed = (event: Event) => {
   const value = (event as CustomEvent<Route>).detail;
   if (!value?.task || !value.model || !value.capability) return;
   lastRoute = value;
   sessionStorage.setItem('sovereign-last-route', JSON.stringify(value));
   void refresh();
  };
  window.addEventListener('sovereign-route', routed);
  const timer = setInterval(() => { if (!document.hidden) void refresh(); }, 15000);
  return () => { clearInterval(timer); window.removeEventListener('sovereign-route', routed); };
 });
</script>

<svelte:window onclick={dismiss} onkeydown={event => { if (event.key === 'Escape') open = false; }} />
<div class="routing-root" bind:this={root}>
 <button class="routing-trigger" class:expanded={open} aria-label="Model and routing" aria-expanded={open} onclick={toggle}>
  <span class="state-dot" class:online={connected && !!generator?.available} class:sleeping={!!generator?.is_sleeping}></span>
  <span class="trigger-copy"><strong>{modelName}</strong>{#if !connected}<small>{initializing ? 'Checking local runtime…' : 'Local backend disconnected'}</small>{/if}</span>
  <ChevronDown size={14} aria-hidden="true" />
 </button>
 {#if open}
  <div class="routing-popover" role="dialog" aria-label="Model and routing details">
   <div class="popover-head"><div><span class="eyebrow">MODEL & ROUTING</span><h2>Local execution</h2></div><button class="refresh" aria-label="Refresh model status" onclick={() => { void details(); }}><RefreshCw size={15}/></button></div>
   <div class="facts">
    <div><span>Currently running</span><strong>{modelName}</strong><small>{runtimeState}{#if generator?.available} · llama.cpp local runtime{/if}</small></div>
    <div><span>Routing</span><strong>{info?.routing?.mode === 'automatic' ? 'Automatic' : initializing ? 'Checking…' : 'Unavailable'}</strong><small>{info?.routing?.mode === 'automatic' ? 'Capability-based selection' : initializing ? 'Reading local registry' : 'Reconnect to inspect routing'}</small></div>
   </div>
   <div class="route-flow" aria-label="Routing flow"><span>Request</span><span>→</span><span>Router</span><span>→</span><span>Local model or tool</span></div>
   <div class="last-route"><span class="eyebrow">LAST RECORDED ROUTE</span>{#if lastRoute}<strong>{lastRoute.task}</strong><p>Selected: {lastRoute.model} ({lastRoute.capability})</p>{#if lastRoute.reason}<p>{lastRoute.reason}</p>{/if}{:else}<p>No routed task has completed in this browser session.</p>{/if}</div>
   <div class="models"><span class="eyebrow">REGISTERED MODELS</span>{#if info?.models?.length}{#each info.models as model}<div class="model-row"><Cpu size={15} aria-hidden="true"/><div><strong>{model.model_id}</strong><small>{model.capability} · {model.context.toLocaleString()} context · {model.quantization}</small></div><span>{!model.enabled ? 'Disabled' : !model.assets_present ? 'Files missing' : generator?.available && generator.alias === model.alias ? generator.is_sleeping ? 'Sleeping' : 'Loaded' : 'Installed'}</span></div>{/each}{:else}<p>Model registry unavailable.</p>{/if}</div>
   <p class="footnote">Code currently uses the registered text model. A separate coding model is not installed. GPU placement is not reported by this status endpoint.</p>
  </div>
 {/if}
</div>

<style>
 .routing-root{position:fixed;top:7px;right:16px;z-index:65;color:var(--foreground);font-size:12px}.routing-trigger{display:flex;align-items:center;gap:9px;width:220px;min-height:36px;padding:6px 10px;border:1px solid var(--border);border-radius:9px;background:color-mix(in srgb,var(--background) 92%,var(--foreground) 8%);box-shadow:0 3px 14px #0002;text-align:left}.routing-trigger:hover,.refresh:hover{background:var(--accent)}.routing-trigger:focus-visible,.refresh:focus-visible{outline:2px solid var(--ring);outline-offset:2px}.state-dot{width:7px;height:7px;flex:none;border-radius:50%;background:var(--muted-foreground)}.state-dot.online{background:var(--chart-2)}.state-dot.sleeping{background:var(--chart-4)}.trigger-copy{min-width:0;flex:1;display:flex;flex-direction:column;gap:2px}.trigger-copy strong{max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px;font-weight:600}.trigger-copy small{color:var(--muted-foreground);font-size:10px}.routing-popover{position:absolute;right:0;top:42px;width:min(370px,calc(100vw - 20px));max-height:min(80dvh,650px);overflow:auto;padding:18px;background:var(--popover);border:1px solid var(--border);border-radius:14px;box-shadow:0 18px 45px #0005}.popover-head,.facts,.model-row{display:flex;justify-content:space-between;gap:12px}.popover-head{align-items:flex-start}.popover-head h2{font-size:17px;font-weight:650;margin-top:3px}.refresh{padding:7px;border-radius:7px}.eyebrow{font-size:9px;font-weight:700;letter-spacing:.12em;color:var(--muted-foreground)}.facts{margin-top:18px}.facts>div{flex:1;min-width:0;display:flex;flex-direction:column;gap:5px}.facts span,.model-row small{color:var(--muted-foreground);font-size:10px}.facts strong{font-size:12px;overflow-wrap:anywhere}.facts small{font-size:10px;color:var(--muted-foreground)}.route-flow{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:18px 0;padding:9px 11px;background:var(--muted);border-radius:8px;font-size:10px}.route-flow span:nth-child(even){color:var(--muted-foreground)}.last-route{padding:15px 0;border-block:1px solid var(--border)}.last-route strong{display:block;margin:7px 0}.last-route p,.models>p,.footnote{font-size:11px;line-height:1.5;color:var(--muted-foreground)}.last-route p+p{margin-top:5px}.models{padding-top:15px}.model-row{align-items:center;padding:11px 0;border-bottom:1px solid var(--border)}.model-row>div{min-width:0;flex:1}.model-row strong{display:block;overflow-wrap:anywhere;font-size:10px}.model-row small{display:block;margin-top:4px}.model-row>span{font-size:10px;white-space:nowrap;color:var(--muted-foreground)}.footnote{margin-top:13px}@media(max-width:640px){.routing-root{right:8px;top:5px}.routing-trigger{width:188px}.trigger-copy strong{max-width:133px}.routing-popover{position:fixed;left:8px;right:8px;top:50px;width:auto}}
 .routing-trigger{
  background:linear-gradient(145deg,color-mix(in srgb,var(--background) 86%,white 14%),color-mix(in srgb,var(--background) 96%,var(--foreground) 4%));
  border-color:color-mix(in srgb,var(--border) 70%,var(--foreground) 30%);
  box-shadow:inset 0 1px #ffffff1c,0 5px 16px #0003;
  -webkit-backdrop-filter:blur(16px) saturate(130%);
  backdrop-filter:blur(16px) saturate(130%);
  transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease,background .18s ease;
 }
 .routing-trigger:hover,.routing-trigger.expanded{
  transform:translateY(-1px);
  border-color:color-mix(in srgb,var(--ring) 48%,var(--border));
  background:linear-gradient(145deg,color-mix(in srgb,var(--background) 78%,white 22%),color-mix(in srgb,var(--background) 91%,var(--foreground) 9%));
  box-shadow:inset 0 1px #ffffff2b,0 9px 25px #0005,0 0 0 3px color-mix(in srgb,var(--ring) 9%,transparent);
 }
 .routing-trigger:active{transform:translateY(0)}
 .routing-trigger :global(svg){flex:none;transition:transform .18s ease}
 .routing-trigger.expanded :global(svg){transform:rotate(180deg)}
 .routing-popover{
  background:color-mix(in srgb,var(--popover) 91%,transparent);
  border-color:color-mix(in srgb,var(--border) 78%,var(--foreground) 22%);
  box-shadow:inset 0 1px #ffffff15,0 22px 55px #0008;
  -webkit-backdrop-filter:blur(24px) saturate(135%);
  backdrop-filter:blur(24px) saturate(135%);
  animation:routing-appear .17s ease-out;
 }
 @keyframes routing-appear{from{opacity:0;transform:translateY(-5px)}to{opacity:1;transform:translateY(0)}}
 @media(prefers-reduced-motion:reduce){.routing-trigger,.routing-trigger :global(svg){transition:none}.routing-popover{animation:none}}
</style>
