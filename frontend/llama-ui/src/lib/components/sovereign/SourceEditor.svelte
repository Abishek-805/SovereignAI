<script module lang="ts">
 import type * as Monaco from 'monaco-editor';
 // Workspace-scoped models retain each file's undo stack and cursor/scroll state.
 // Bound retention so browsing many files cannot accumulate unbounded editor memory.
 const retainedModels = new Map<string,{model:Monaco.editor.ITextModel;view:Monaco.editor.ICodeEditorViewState|null}>();
 const MODEL_LIMIT=24;
 let editorPreferences:{minimap:boolean;wordWrap:'off'|'on'}={minimap:false,wordWrap:'off'};
</script>
<script lang="ts">
 import { onMount } from 'svelte';
 let { value = $bindable(''), filename = '', workspaceId='', readOnly=false, revealLine=0, revealNonce=0, onsave = (_:string) => {}, onmarkers = (_: {line:number;message:string;severity:number}[]) => {} }: { value?:string; filename?:string; workspaceId?:string; readOnly?:boolean; revealLine?:number; revealNonce?:number; onsave?:(content:string)=>void;onmarkers?:(markers:{line:number;message:string;severity:number}[])=>void } = $props();
 let container: HTMLDivElement;
 let editor: Monaco.editor.IStandaloneCodeEditor | undefined;
 let api: typeof Monaco | undefined;
 let ready = $state(false);
 let failure = $state('');
 let lastReveal=0;
 const languages:Record<string,string> = {py:'python',js:'javascript',mjs:'javascript',ts:'typescript',tsx:'typescript',jsx:'javascript',java:'java',c:'c',h:'c',cpp:'cpp',cc:'cpp',go:'go',rs:'rust',php:'php',rb:'ruby',html:'html',css:'css',json:'json',md:'markdown',sh:'shell',sql:'sql',yaml:'yaml',yml:'yaml',xml:'xml',toml:'ini'};
 Object.assign(languages,{cjs:'javascript',cxx:'cpp',hpp:'cpp',cs:'csharp',r:'r',lua:'lua',pl:'perl',bash:'shell',htm:'html',kt:'kotlin',kts:'kotlin',swift:'swift',dart:'dart',scala:'scala',vue:'html',scss:'scss',less:'less',markdown:'markdown',ps1:'powershell',fs:'fsharp',ex:'elixir',exs:'elixir'});
 const language=(name:string)=>languages[(name.split('.').pop()||'').toLowerCase()]||'plaintext';
 onMount(() => {
  let disposed=false;
  let listener: Monaco.IDisposable | undefined;
  let markerListener: Monaco.IDisposable | undefined;
  let themeObserver: MutationObserver | undefined;
  let retainedKey='';
  let actionListener: ((event: Event) => void) | undefined;
  void (async()=>{
   try {
    const [{default:Worker},{default:TsWorker},{default:JsonWorker},{default:HtmlWorker},{default:CssWorker},monaco] = await Promise.all([import('monaco-editor/esm/vs/editor/editor.worker?worker'),import('monaco-editor/esm/vs/language/typescript/ts.worker?worker'),import('monaco-editor/esm/vs/language/json/json.worker?worker'),import('monaco-editor/esm/vs/language/html/html.worker?worker'),import('monaco-editor/esm/vs/language/css/css.worker?worker'),import('monaco-editor')]);
    if(disposed)return;
    (globalThis as typeof globalThis & {MonacoEnvironment:unknown}).MonacoEnvironment={getWorker:(_:string,label:string)=>label==='typescript'||label==='javascript'?new TsWorker():label==='json'?new JsonWorker():label==='html'?new HtmlWorker():['css','scss','less'].includes(label)?new CssWorker():new Worker()};
    api=monaco;
    try{const stored=JSON.parse(localStorage.getItem('sovereign-editor-preferences')||'{}');editorPreferences={minimap:stored.minimap===true,wordWrap:stored.wordWrap==='on'?'on':'off'};}catch{}
    retainedKey=workspaceId&&filename?workspaceId+':'+filename:'';
    let retained=retainedKey?retainedModels.get(retainedKey):undefined;
    if(retained?.model.isDisposed()){retainedModels.delete(retainedKey);retained=undefined;}
    const model=retained?.model||monaco.editor.createModel(value,language(filename),retainedKey?monaco.Uri.parse('sovereign-file:///'+encodeURIComponent(workspaceId)+'/'+filename.split('/').map(encodeURIComponent).join('/')):undefined);
    if(model.getValue()!==value)model.setValue(value);
    if(retainedKey){retainedModels.delete(retainedKey);retainedModels.set(retainedKey,{model,view:retained?.view||null});}
    while(retainedModels.size>MODEL_LIMIT){const oldest=retainedModels.keys().next().value!;retainedModels.get(oldest)?.model.dispose();retainedModels.delete(oldest);}
    editor=monaco.editor.create(container,{model,readOnly,theme:document.documentElement.classList.contains('dark')?'vs-dark':'vs',automaticLayout:true,minimap:{enabled:editorPreferences.minimap},fontSize:13,lineNumbers:'on',scrollBeyondLastLine:false,wordWrap:editorPreferences.wordWrap,padding:{top:12},tabSize:4});
    if(retained?.view)editor.restoreViewState(retained.view);
    themeObserver=new MutationObserver(()=>monaco.editor.setTheme(document.documentElement.classList.contains('dark')?'vs-dark':'vs'));
    themeObserver.observe(document.documentElement,{attributes:true,attributeFilter:['class']});
    listener=editor.onDidChangeModelContent(()=>{value=editor!.getValue();});
    const reportMarkers=()=>{const model=editor?.getModel();if(model)onmarkers(monaco.editor.getModelMarkers({resource:model.uri}).map(marker=>({line:marker.startLineNumber,message:marker.message,severity:marker.severity})));};
    markerListener=monaco.editor.onDidChangeMarkers(reportMarkers);
    reportMarkers();
    editor.addCommand(monaco.KeyMod.CtrlCmd|monaco.KeyCode.KeyS,()=>onsave(editor!.getValue()));
    const nativeActions=new Set(['actions.find','editor.action.startFindReplaceAction','editor.action.commentLine','editor.action.blockComment','editor.action.insertCursorAbove','editor.action.insertCursorBelow','editor.action.addSelectionToNextFindMatch','editor.action.jumpToBracket','editor.action.quickOutline','editor.action.formatDocument','editor.action.selectAll','editor.action.selectHighlights']);
    const persistPreferences=()=>{try{localStorage.setItem('sovereign-editor-preferences',JSON.stringify(editorPreferences));}catch{}};
    actionListener=(event:Event)=>{
     const action=(event as CustomEvent<{action:string}>).detail?.action;
     if(!editor||!action)return;
     editor.focus();
     if(action==='toggle-word-wrap'){editorPreferences.wordWrap=editor.getOption(monaco.editor.EditorOption.wordWrap)==='off'?'on':'off';editor.updateOptions({wordWrap:editorPreferences.wordWrap});persistPreferences();return;}
     if(action==='toggle-minimap'){editorPreferences.minimap=!editor.getOption(monaco.editor.EditorOption.minimap).enabled;editor.updateOptions({minimap:{enabled:editorPreferences.minimap}});persistPreferences();return;}
     if(action==='undo'||action==='redo'||action==='selectAll'){editor.trigger('sovereign',action,null);return;}
     if(nativeActions.has(action)){const command=editor.getAction(action);if(command?.isSupported())void command.run().catch(error=>{if(!(error instanceof Error&&error.name==='Canceled'))failure=String(error);});}
    };
    window.addEventListener('sovereign-editor-action',actionListener);
    ready=true;
   }catch(error){failure=String(error);}
  })();
  return ()=>{disposed=true;listener?.dispose();markerListener?.dispose();themeObserver?.disconnect();if(actionListener)window.removeEventListener('sovereign-editor-action',actionListener);const retained=retainedModels.get(retainedKey);if(retained&&editor)retained.view=editor.saveViewState();else editor?.getModel()?.dispose();editor?.dispose();};
 });
 $effect(()=>{ const text=value; const name=filename; const locked=readOnly; if(ready && editor && api){editor.updateOptions({readOnly:locked});if(editor.getValue()!==text)editor.setValue(text);const model=editor.getModel();if(model)api.editor.setModelLanguage(model,language(name));}});
 $effect(()=>{const line=revealLine,nonce=revealNonce;if(ready&&editor&&line>0&&nonce!==lastReveal){lastReveal=nonce;editor.setPosition({lineNumber:line,column:1});editor.revealLineInCenter(line);if(!(document.activeElement instanceof Element)||!document.activeElement.closest('[role="dialog"],.palette'))editor.focus();}});
</script>
<div class="source-editor" bind:this={container} aria-label="Source editor"></div>
{#if failure}<p role="alert">Editor failed to load: {failure}</p><textarea aria-label="Source" bind:value></textarea>{/if}
<style>.source-editor{height:100%;min-height:320px;min-width:0;}textarea{width:100%;min-height:320px;font-family:monospace;}</style>
