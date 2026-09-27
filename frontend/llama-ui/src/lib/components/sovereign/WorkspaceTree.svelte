<script lang="ts">
 import { FileCode, Folder } from '@lucide/svelte';
 let { files, folders=[], selected, cut='', onselect, oncontext }: {files:string[];folders?:string[];selected:string;cut?:string;onselect:(name:string)=>void;oncontext:(path:string,kind:'file'|'folder',x:number,y:number)=>void}=$props();
 type Node={name:string;path:string;children:Node[];file:boolean};
 let tree=$derived.by(()=>{const roots:Node[]=[];for(const path of [...folders.map(p=>p+'/'),...files].sort()){let nodes=roots;const parts=path.replace(/\/$/,'').split('/');for(let i=0;i<parts.length;i++){let node=nodes.find(n=>n.name===parts[i]);if(!node){node={name:parts[i],path:parts.slice(0,i+1).join('/'),children:[],file:!path.endsWith('/')&&i===parts.length-1};nodes.push(node);}nodes=node.children;}}return roots;});
</script>
{#snippet branch(nodes:Node[])}
 {#each nodes as node}
  {#if node.file}<button class:active={selected===node.path} class:cut={cut===node.path} title={node.path} onclick={()=>onselect(node.path)} oncontextmenu={e=>{e.preventDefault();e.stopPropagation();oncontext(node.path,'file',e.clientX,e.clientY);}} onkeydown={e=>{if(e.key==='ContextMenu'||(e.shiftKey&&e.key==='F10')){e.preventDefault();const rect=e.currentTarget.getBoundingClientRect();oncontext(node.path,'file',rect.left+24,rect.bottom);}}}><FileCode size={14}/><span>{node.name}</span></button>
  {:else}<details open><summary tabindex="0" title={node.path} oncontextmenu={e=>{e.preventDefault();e.stopPropagation();oncontext(node.path,'folder',e.clientX,e.clientY);}} onkeydown={e=>{if(e.key==='ContextMenu'||(e.shiftKey&&e.key==='F10')){e.preventDefault();const rect=e.currentTarget.getBoundingClientRect();oncontext(node.path,'folder',rect.left+24,rect.bottom);}}}><Folder size={14}/>{node.name}</summary><div class="children">{@render branch(node.children)}</div></details>{/if}
 {/each}
{/snippet}
<div class="tree" aria-label="Workspace files">{@render branch(tree)}</div>
<style>.tree{font-size:12px;}button,summary{display:flex;align-items:center;gap:7px;width:100%;padding:6px 8px;cursor:pointer;white-space:nowrap;text-align:left;}button:hover,summary:hover{background:var(--accent);}button.active{background:var(--accent);color:var(--foreground);}button.cut{opacity:.45;}button span{overflow:hidden;text-overflow:ellipsis;}summary{font-weight:500;}.children{padding-left:12px;}</style>
