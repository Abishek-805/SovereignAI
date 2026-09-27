<script lang="ts">
 import { onMount } from 'svelte';
 import type * as Monaco from 'monaco-editor';
 let { value = $bindable(''), filename = '', readOnly=false, revealLine=0, revealNonce=0, onsave = (_:string) => {}, onmarkers = (_: {line:number;message:string;severity:number}[]) => {} }: { value?:string; filename?:string; readOnly?:boolean; revealLine?:number; revealNonce?:number; onsave?:(content:string)=>void;onmarkers?:(markers:{line:number;message:string;severity:number}[])=>void } = $props();
 let container: HTMLDivElement;
 let editor: Monaco.editor.IStandaloneCodeEditor | undefined;
 let api: typeof Monaco | undefined;
 let ready = $state(false);
 let failure = $state('');
 let lastReveal=0;
 const languages:Record<string,string> = {py:'python',js:'javascript',mjs:'javascript',ts:'typescript',tsx:'typescript',jsx:'javascript',java:'java',c:'c',h:'c',cpp:'cpp',cc:'cpp',go:'go',rs:'rust',php:'php',rb:'ruby',html:'html',css:'css',json:'json',md:'markdown',sh:'shell',sql:'sql',yaml:'yaml',yml:'yaml',xml:'xml',toml:'ini'};
 const language=(name:string)=>languages[name.split('.').pop()||'']||'plaintext';
 onMount(() => {
  let disposed=false;
  let listener: Monaco.IDisposable | undefined;
  let markerListener: Monaco.IDisposable | undefined;
  void (async()=>{
   try {
    const [{default:Worker},{default:TsWorker},{default:JsonWorker},{default:HtmlWorker},{default:CssWorker},monaco] = await Promise.all([import('monaco-editor/esm/vs/editor/editor.worker?worker'),import('monaco-editor/esm/vs/language/typescript/ts.worker?worker'),import('monaco-editor/esm/vs/language/json/json.worker?worker'),import('monaco-editor/esm/vs/language/html/html.worker?worker'),import('monaco-editor/esm/vs/language/css/css.worker?worker'),import('monaco-editor')]);
    if(disposed)return;
    (globalThis as typeof globalThis & {MonacoEnvironment:unknown}).MonacoEnvironment={getWorker:(_:string,label:string)=>label==='typescript'||label==='javascript'?new TsWorker():label==='json'?new JsonWorker():label==='html'?new HtmlWorker():['css','scss','less'].includes(label)?new CssWorker():new Worker()};
    api=monaco;
    editor=monaco.editor.create(container,{value,readOnly,language:language(filename),theme:document.documentElement.classList.contains('dark')?'vs-dark':'vs',automaticLayout:true,minimap:{enabled:false},fontSize:13,lineNumbers:'on',scrollBeyondLastLine:false,wordWrap:'off',padding:{top:12},tabSize:4});
    listener=editor.onDidChangeModelContent(()=>{value=editor!.getValue();});
    const reportMarkers=()=>{const model=editor?.getModel();if(model)onmarkers(monaco.editor.getModelMarkers({resource:model.uri}).map(marker=>({line:marker.startLineNumber,message:marker.message,severity:marker.severity})));};
    markerListener=monaco.editor.onDidChangeMarkers(reportMarkers);
    editor.addCommand(monaco.KeyMod.CtrlCmd|monaco.KeyCode.KeyS,()=>onsave(editor!.getValue()));
    ready=true;
   }catch(error){failure=String(error);}
  })();
  return ()=>{disposed=true;listener?.dispose();markerListener?.dispose();editor?.getModel()?.dispose();editor?.dispose();};
 });
 $effect(()=>{ const text=value; const name=filename; const locked=readOnly; if(ready && editor && api){editor.updateOptions({readOnly:locked});if(editor.getValue()!==text)editor.setValue(text);const model=editor.getModel();if(model)api.editor.setModelLanguage(model,language(name));}});
 $effect(()=>{const line=revealLine,nonce=revealNonce;if(ready&&editor&&line>0&&nonce!==lastReveal){lastReveal=nonce;editor.setPosition({lineNumber:line,column:1});editor.revealLineInCenter(line);editor.focus();}});
</script>
<div class="source-editor" bind:this={container} aria-label="Source editor"></div>
{#if failure}<p role="alert">Editor failed to load: {failure}</p><textarea aria-label="Source" bind:value></textarea>{/if}
<style>.source-editor{height:100%;min-height:320px;min-width:0;}textarea{width:100%;min-height:320px;font-family:monospace;}</style>
