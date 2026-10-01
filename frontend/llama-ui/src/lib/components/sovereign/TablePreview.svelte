<script lang="ts">
 import { knowledgeJson } from '$lib/services/knowledge.service';
 import {untrack,onDestroy,tick} from 'svelte';
 import { nextMatchIndex, tableFindParams } from '$lib/services/workspace-ui-state';
 let { documentId }: {documentId:string}=$props();
 type Cell={coordinate:string;value:string|number|boolean|null;bold?:boolean;italic?:boolean;color?:string;fill?:string;align?:string;format?:string};
 type Preview={sheets:{name:string;row_count:number;column_count:number}[];sheet:number;name:string;offset:number;total:number;rows:{number:number;cells:Cell[]}[];merges:string[];widths:Record<string,number>};
 let data=$state<Preview|null>(null),sheet=$state(0),error=$state(''),loading=$state(false),jump=$state(1);
 let viewport:HTMLDivElement; let sequence=0; let timer:ReturnType<typeof setTimeout>;
 type Match={sheet:number;name:string;row:number;column:number;coordinate:string;value:string|number|boolean|null};
 let findText=$state(''),finding=$state(false),findError=$state('');
 let matches=$state<Match[]>([]),matchTotal=$state(0),matchOffset=$state(0),matchIndex=$state(-1),activeMatch=$state<Match|null>(null),searched=$state(false);
 let findSequence=0,searchKey='';
 let selected=$state('A1'),address=$state('A1');
 const selectedRow=$derived(coordinate(selected)[0]);
 const selectedCell=$derived(data?.rows.flatMap(row=>row.cells).find(cell=>cell.coordinate===selected));
 async function selectCell(value:string,focus=false){
  const [row,col]=coordinate(value.toUpperCase().trim());
  if(!data||row<1||row>data.total||col<1||col>data.sheets[sheet].column_count){error='Enter a cell address within this worksheet.';return;}
  selected=column(col-1)+row;address=selected;error='';
  if(row<=data.offset||row>data.offset+data.rows.length)await load(Math.floor((row-1)/50)*50);
  await tick();
  viewport?.querySelector<HTMLElement>(`[data-coordinate="${selected}"]`)?.scrollIntoView({block:'nearest',inline:'nearest'});
  if(focus)viewport?.focus({preventScroll:true});
 }
 function navigateCell(event:KeyboardEvent){
  if(event.target!==viewport||!data)return;
  let [row,col]=coordinate(selected);
  const step=Math.max(1,Math.floor((viewport.clientHeight-30)/30));
  switch(event.key){
   case 'ArrowUp':row--;break;case 'ArrowDown':row++;break;
   case 'ArrowLeft':col--;break;case 'ArrowRight':col++;break;
   case 'PageUp':row-=step;break;case 'PageDown':row+=step;break;
   case 'Home':col=1;if(event.ctrlKey)row=1;break;
   case 'End':col=data.sheets[sheet].column_count;if(event.ctrlKey)row=data.total;break;
   default:return;
  }
  event.preventDefault();void selectCell(column(Math.max(1,Math.min(col,data.sheets[sheet].column_count))-1)+Math.max(1,Math.min(row,data.total)));
 }
 function currentSearchKey(){return JSON.stringify([documentId,findText,sheet]);}
 function resetFind(){clearTimeout(timer);findSequence++;matches=[];matchTotal=0;matchIndex=-1;activeMatch=null;searched=false;findError='';finding=false;searchKey='';}
 function searchAsYouType(event:Event){findText=(event.currentTarget as HTMLInputElement).value;resetFind();if(findText)void find();}
 async function matchPage(offset:number,request:number){
  const params=tableFindParams(findText,false,false,offset,sheet);
  const result=await knowledgeJson(await fetch(`/documents/${encodeURIComponent(documentId)}/table/find?${params}`));
  if(request!==findSequence)return false;
  matches=result.matches;matchTotal=result.total;matchOffset=result.offset;return true;
 }
 async function revealMatch(index:number,request:number){
  if(index<matchOffset||index>=matchOffset+matches.length){if(!await matchPage(Math.floor(index/200)*200,request))return;}
  const match=matches[index-matchOffset];if(!match||request!==findSequence)return;
  activeMatch=match;matchIndex=index;sheet=match.sheet;selected=match.coordinate;address=selected;jump=match.row;clearTimeout(timer);
  await load(Math.max(0,Math.floor((match.row-1)/50)*50),()=>request===findSequence);await tick();
  if(request!==findSequence)return;
  if(viewport)viewport.scrollTop=(match.row-1)*30;
  viewport?.querySelector<HTMLElement>(`[data-coordinate="${match.coordinate}"]`)?.scrollIntoView({block:'nearest',inline:'nearest'});
 }
 async function find(direction=1){
  if(!findText||finding)return;
  const request=++findSequence;finding=true;findError='';
  try{
   if(searchKey!==currentSearchKey()){const key=currentSearchKey();activeMatch=null;matchIndex=-1;if(!await matchPage(0,request))return;searchKey=key;searched=true;}
   if(matchTotal)await revealMatch(matchIndex<0?(direction<0?matchTotal-1:0):nextMatchIndex(matchIndex,direction,matchTotal),request);
  }catch(e){if(request===findSequence)findError=String(e);}finally{if(request===findSequence)finding=false;}
 }
 function boundedOffset(offset:number){return Math.max(0,Math.min(offset,Math.max(0,(data?.total||100)-100)));}
 async function load(offset=0,isCurrent=()=>true){offset=boundedOffset(offset);const request=++sequence;loading=true;error='';try{const result=await knowledgeJson(await fetch(`/documents/${documentId}/table?sheet=${sheet}&offset=${offset}&limit=100`));if(request===sequence&&isCurrent())data=result;}catch(e){if(request===sequence&&isCurrent())error=String(e);}finally{if(request===sequence)loading=false;}}
 let loadedDocument='';
 $effect(()=>{const id=documentId;if(id===loadedDocument)return;loadedDocument=id;untrack(()=>{resetFind();sheet=0;selected='A1';address=selected;data=null;jump=1;if(viewport){viewport.scrollTop=0;viewport.scrollLeft=0;}void load();});});
 onDestroy(()=>{sequence++;findSequence++;clearTimeout(timer);});
 function choose(index:number){resetFind();selected='A1';address=selected;sheet=index;data=null;if(viewport){viewport.scrollTop=0;viewport.scrollLeft=0;}void load();}
 function scroll(){if(!data)return;const offset=boundedOffset(Math.floor(viewport.scrollTop/30/50)*50);if(offset!==data.offset){clearTimeout(timer);timer=setTimeout(()=>void load(offset),100);}}

 function column(index:number){let result='';for(let n=index+1;n>0;n=Math.floor((n-1)/26))result=String.fromCharCode(65+(n-1)%26)+result;return result;}
 function coordinate(value:string){const m=/^([A-Z]+)(\d+)$/.exec(value);if(!m)return [0,0];return [Number(m[2]),[...m[1]].reduce((a,c)=>a*26+c.charCodeAt(0)-64,0)];}
 function merge(cell:Cell){for(const range of data?.merges||[]){const [a,b]=range.split(':').map(coordinate),[r,c]=coordinate(cell.coordinate);if(r>=a[0]&&r<=b[0]&&c>=a[1]&&c<=b[1])return r===a[0]&&c===a[1]?{colspan:b[1]-a[1]+1,rowspan:b[0]-a[0]+1,hidden:false}:{colspan:1,rowspan:1,hidden:true};}return {colspan:1,rowspan:1,hidden:false};}
 function display(cell:Cell){const value=cell.value;if(value==null)return '';if(typeof value==='number'&&cell.format&&cell.format!=='General'){const decimals=/\.([0#]+)/.exec(cell.format)?.[1].length;if(cell.format.includes('%'))return (value*100).toFixed(decimals||0)+'%';if(decimals!==undefined)return value.toFixed(Math.min(decimals,12));}return String(value);}
</script>
<div class="sheet-preview" aria-label="Original table preview">
 <div class="sheet-toolbar"><strong>{data?.name||'Worksheet'}</strong><span>{data?.total||0} rows</span><span role="status">{loading?'Loading rows…':''}</span>
 <div class="cell-bar"><input aria-label="Cell address" bind:value={address} onkeydown={e=>{if(e.key==='Enter'){e.preventDefault();void selectCell(address,true);}}}/><span class="cell-value" aria-label="Selected cell value">{selectedCell?display(selectedCell):''}</span></div>
 <div class="sheet-find" aria-label="Find in selected worksheet">
  <label>Find <input aria-label="Find cell values" type="search" bind:value={findText} oninput={searchAsYouType} onkeydown={e=>{if(e.key==='Enter'){e.preventDefault();void find(e.shiftKey?-1:1);}}} /></label>
  <button onclick={()=>void find(-1)} disabled={!findText||finding}>Previous</button><button onclick={()=>void find(1)} disabled={!findText||finding}>Next</button>
  <span role="status">{finding?'Finding…':searched?(matchTotal?`${matchIndex+1} of ${matchTotal} · ${activeMatch?.name||''}!${activeMatch?.coordinate||''}`:'No matches'):''}</span>
  {#if findError}<span role="alert">{findError}</span>{/if}
 </div></div>
 {#if error}<p role="alert">{error}<button onclick={()=>void load()}>Retry</button></p>{/if}
 <!-- The focusable scroll region handles worksheet navigation while preserving native table semantics. -->
 <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
 <div class="sheet-scroll" role="region" aria-label="Worksheet cells, use arrow keys to navigate" tabindex="0" bind:this={viewport} onscroll={scroll} onkeydown={navigateCell}>
 {#if data}<table aria-label={data.name}><colgroup><col style="width:48px" />{#each Array.from({length:data.sheets[sheet].column_count}) as _,i}<col style:width={(data.widths[column(i)]||18)*7+'px'} />{/each}</colgroup><thead><tr><th aria-label="Row number"></th>{#each Array.from({length:data.sheets[sheet].column_count}) as _,i}<th>{column(i)}</th>{/each}</tr></thead><tbody>
 {#if data.offset}<tr aria-hidden="true" class="spacer"><td colspan={data.sheets[sheet].column_count+1} style:height={data.offset*30+'px'}></td></tr>{/if}
 {#each data.rows as row}<tr class:selected-row={selectedRow===row.number}><th><button class="row-select" aria-label={'Select row '+row.number} onclick={()=>void selectCell('A'+row.number,true)}>{row.number}</button></th>{#each row.cells as cell}{@const merged=merge(cell)}{#if !merged.hidden}<td class:selected-cell={selected===cell.coordinate} data-coordinate={cell.coordinate} colspan={merged.colspan} rowspan={merged.rowspan} title={cell.coordinate+(cell.format?' · '+cell.format:'')} style:background={cell.fill?'color-mix(in srgb, #'+cell.fill+' 18%, var(--background))':undefined} style:font-weight={cell.bold?'700':'400'} style:font-style={cell.italic?'italic':'normal'}  style:text-align={cell.align==='general'?(typeof cell.value==='number'?'right':'left'):cell.align}><button class="cell-select" tabindex="-1" onclick={()=>void selectCell(cell.coordinate,true)} aria-label={display(cell)||cell.coordinate}>{display(cell)}</button></td>{/if}{/each}</tr>{/each}
 {#if data.offset+data.rows.length<data.total}<tr aria-hidden="true" class="spacer"><td colspan={data.sheets[sheet].column_count+1} style:height={(data.total-data.offset-data.rows.length)*30+'px'}></td></tr>{/if}
 </tbody></table>{:else if loading}<p role="status">Reading the original worksheet…</p>{/if}
 </div>
 <nav aria-label="Worksheets">{#each data?.sheets||[] as item,i}<button aria-pressed={sheet===i} onclick={()=>choose(i)}>{item.name}</button>{/each}</nav>
 <small>Original cell values with theme-adapted formatting. Formulas are shown using saved results; charts and conditional formatting are available in the downloaded original.</small>
</div>
<style>
.sheet-preview{height:100%;display:flex;flex-direction:column;min-height:0}.sheet-toolbar{display:flex;gap:16px;align-items:center;padding:10px 14px;border-bottom:1px solid var(--border);font-size:12px;flex-wrap:wrap}.sheet-toolbar input{width:100px;min-width:100px;height:32px;box-sizing:border-box;background:var(--background);color:var(--foreground);font:inherit;border:1px solid var(--border);border-radius:5px;padding:4px 8px}.sheet-scroll{flex:1;overflow:auto;background:var(--background);min-height:0;color:var(--foreground)}table{border-collapse:separate;border-spacing:0;table-layout:fixed;min-width:100%;font:13px Arial,sans-serif}th,td{height:30px;box-sizing:border-box;padding:4px 8px;border-right:1px solid var(--border);border-bottom:1px solid var(--border);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:500px}thead{position:sticky;top:0;z-index:2}th{background:var(--muted,var(--background));color:var(--muted-foreground);text-align:center;font-weight:400}tbody th{position:sticky;left:0;z-index:1}.spacer td{padding:0;border:0}nav{display:flex;gap:4px;padding:8px;background:var(--background);border-top:1px solid var(--border);overflow:auto}button{padding:5px 12px;border:1px solid var(--border);border-radius:5px;white-space:nowrap}nav button[aria-pressed=true]{color:var(--wb-focus);border-color:var(--wb-focus)}small{padding:5px 14px;color:var(--muted-foreground);font-size:11px}
.sheet-find{display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:12px}.sheet-find label{display:flex;align-items:center;gap:6px}.sheet-find input{background:var(--background);color:var(--foreground);border:1px solid var(--border);border-radius:5px;padding:6px;min-height:32px}.sheet-find input[type=search]{width:190px}.sheet-find [role=status]{color:var(--muted-foreground)}.sheet-toolbar button{min-height:32px}.sheet-toolbar label{white-space:nowrap}
.cell-bar{display:flex;gap:8px;align-items:center;min-width:0;flex:1;max-width:320px}.cell-bar input{width:88px;background:var(--background);color:var(--foreground);border:1px solid var(--border);border-radius:4px;padding:5px 8px}.cell-value{min-width:0;flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;font-size:12px}.row-select{padding:0;border:0;width:100%;background:transparent;color:inherit;border-radius:0}.selected-row td{background:color-mix(in srgb,var(--wb-focus) 12%,var(--background))!important}td.selected-cell{outline:2px solid var(--wb-focus);outline-offset:-2px}.sheet-scroll{scrollbar-color:var(--muted-foreground) var(--background);scrollbar-gutter:stable}.sheet-scroll:focus-visible{outline:1px solid var(--wb-focus);outline-offset:-1px}.sheet-find{margin-left:auto}
.cell-select{display:block;width:100%;padding:0;border:0;border-radius:0;background:transparent;color:inherit;font:inherit;font-weight:inherit;font-style:inherit;text-align:inherit;overflow:hidden;text-overflow:ellipsis;min-height:20px}
</style>
