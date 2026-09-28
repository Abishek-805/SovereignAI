<script lang="ts">
 import { onMount } from 'svelte';
 let { src, name }: { src: string; name: string } = $props();
 let viewport: HTMLDivElement;
 let width=$state(0), height=$state(0), naturalWidth=$state(0), naturalHeight=$state(0);
 let scale=$state(1), x=$state(0), y=$state(0), fitted=$state(true), dragging=$state(false);
 let drag:{id:number;x:number;y:number;originX:number;originY:number}|null=null;
 const fitScale=$derived(naturalWidth&&naturalHeight?Math.max(.05,Math.min((width-32)/naturalWidth,(height-32)/naturalHeight,1)):1);
 $effect(()=>{src;naturalWidth=0;naturalHeight=0;fitted=true;x=0;y=0;});
 $effect(()=>{if(fitted&&fitScale>0)scale=fitScale;});
 function fit(){fitted=true;scale=fitScale;x=0;y=0;}
 function zoom(next:number){fitted=false;scale=Math.max(.05,Math.min(16,next));}
 function pointerDown(event:PointerEvent){if(event.button!==0)return;event.preventDefault();viewport.setPointerCapture(event.pointerId);drag={id:event.pointerId,x:event.clientX,y:event.clientY,originX:x,originY:y};dragging=true;}
 function pointerMove(event:PointerEvent){if(!drag||drag.id!==event.pointerId)return;x=drag.originX+event.clientX-drag.x;y=drag.originY+event.clientY-drag.y;}
 function pointerEnd(event:PointerEvent){if(drag?.id!==event.pointerId)return;drag=null;dragging=false;}
 onMount(()=>{const observer=new ResizeObserver(([entry])=>{width=entry.contentRect.width;height=entry.contentRect.height;});observer.observe(viewport);return()=>observer.disconnect();});
</script>
<div class="image-viewer">
 <div class="image-toolbar" aria-label="Image preview controls">
  <button onclick={()=>zoom(scale/1.25)} aria-label="Zoom out">−</button><output aria-live="polite">{Math.round(scale*100)}%</output><button onclick={()=>zoom(scale*1.25)} aria-label="Zoom in">+</button>
  <button onclick={fit} aria-pressed={fitted}>Fit</button><button onclick={()=>{zoom(1);x=0;y=0;}}>Actual size</button><button onclick={fit}>Reset</button><span>{naturalWidth&&naturalHeight?`${naturalWidth} × ${naturalHeight}`:''}</span>
 </div>
 <!-- A dedicated image element never executes SVG scripts or exposes an inline SVG DOM. -->
 <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
 <div class="image-viewport" class:dragging bind:this={viewport} role="img" aria-label={'Preview '+name+'; drag to pan, use controls to zoom'} onpointerdown={pointerDown} onpointermove={pointerMove} onpointerup={pointerEnd} onpointercancel={pointerEnd} onlostpointercapture={pointerEnd} onwheel={(event)=>{event.preventDefault();zoom(scale*(event.deltaY<0?1.1:1/1.1));}}>
  <img {src} alt={name} draggable="false" onload={(event)=>{const image=event.currentTarget as HTMLImageElement;naturalWidth=image.naturalWidth;naturalHeight=image.naturalHeight;fit();}} style:width={naturalWidth+'px'} style:height={naturalHeight+'px'} style:transform={`translate(${x}px,${y}px) scale(${scale})`} />
 </div>
</div>
<style>
 .image-viewer{height:100%;width:100%;min-height:0;display:flex;flex-direction:column;background:var(--background)}
 .image-toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:8px 12px;border-bottom:1px solid var(--border);font-size:12px;flex:none}
 .image-toolbar button{padding:4px 8px;border:1px solid var(--border);border-radius:5px;background:var(--wb-surface);color:var(--foreground)}
 .image-toolbar button:hover,.image-toolbar button[aria-pressed='true']{background:var(--accent)}
 .image-toolbar button:focus-visible{outline:2px solid var(--wb-focus);outline-offset:2px}
 .image-toolbar output{min-width:42px;text-align:center;font-variant-numeric:tabular-nums}.image-toolbar span{margin-left:auto;color:var(--muted-foreground)}
 .image-viewport{flex:1;min-height:0;overflow:hidden;display:flex;align-items:center;justify-content:center;touch-action:none;cursor:grab;user-select:none;background:repeating-conic-gradient(color-mix(in srgb,var(--muted) 25%,transparent) 0% 25%,transparent 0% 50%) 50% / 20px 20px}
 .image-viewport.dragging{cursor:grabbing}.image-viewport img{max-width:none;max-height:none;flex:none;object-fit:contain;transform-origin:center;pointer-events:none}
</style>
