<script lang="ts">
 import { routeFacts, routingModel, type RoutingTelemetry } from '$lib/services/routing-telemetry';
 import { modelDisplayName } from '$lib/utils/model-display-name';
 let { routing, compact=false }: { routing?: RoutingTelemetry | null; compact?: boolean }=$props();
 const facts=$derived(routeFacts(routing));
 const model=$derived(routingModel(routing));
</script>
{#if facts.length}
 <div class="route-observation" class:compact>
  {#if model}<span class="route-model" title={model}>Automatic · {modelDisplayName(model)}</span>{/if}
  <details class="route-details"><summary>Route details <span aria-hidden="true">· Why?</span></summary>
   <div class="route-facts" aria-label="Routing decision"><strong>Routing decision</strong><dl>{#each facts as fact}<div><dt>{fact.label}</dt><dd>{fact.value}</dd></div>{/each}</dl></div>
  </details>
 </div>
{/if}
<style>
 .route-observation{min-width:0;max-width:100%;margin:8px 0;font-size:11px;line-height:1.5;color:var(--muted-foreground)}
 .route-model{display:block;overflow-wrap:anywhere;margin-bottom:3px}
 summary{cursor:pointer;width:fit-content;border-radius:4px;padding:2px 0;color:var(--foreground)}
 summary:focus-visible{outline:2px solid var(--ring);outline-offset:3px}
 summary span{color:var(--muted-foreground)}
 .route-facts{margin-top:8px;padding:12px;border:1px solid var(--border);border-radius:8px;background:var(--muted);color:var(--foreground);max-height:360px;overflow:auto;max-width:100%;box-sizing:border-box}
 .route-facts>strong{display:block;margin-bottom:8px;font-size:12px}
 dl{margin:0}dl>div{display:grid;grid-template-columns:minmax(90px,30%) minmax(0,1fr);gap:10px;padding:6px 0;border-top:1px solid var(--border)}
 dt{color:var(--muted-foreground)}dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;min-width:0;font-variant-numeric:tabular-nums}
 .compact dl>div{display:block}.compact dd{margin-top:3px}
 @media(max-width:480px){dl>div{display:block}dd{margin-top:3px}}
</style>
