<script lang="ts">
 import { onMount } from 'svelte';
 import type * as Monaco from 'monaco-editor';

 let { original, modified, filename }: { original: string; modified: string; filename: string } = $props();
 let container: HTMLDivElement;
 let failure = $state('');
 let ready=$state(false);
 let editor: Monaco.editor.IStandaloneDiffEditor | undefined;
 let before: Monaco.editor.ITextModel | undefined;
 let after: Monaco.editor.ITextModel | undefined;
 const languages: Record<string, string> = {py:'python',js:'javascript',mjs:'javascript',ts:'typescript',tsx:'typescript',jsx:'javascript',java:'java',c:'c',h:'c',cpp:'cpp',cc:'cpp',go:'go',rs:'rust',php:'php',rb:'ruby',html:'html',css:'css',json:'json',md:'markdown',sh:'shell',sql:'sql',yaml:'yaml',yml:'yaml'};

 onMount(() => {
  let disposed = false;
  let themeObserver: MutationObserver | undefined;
  void (async () => {
   try {
    const [{ default: Worker }, { default: TsWorker }, { default: JsonWorker }, { default: HtmlWorker }, { default: CssWorker }, monaco] = await Promise.all([
     import('monaco-editor/esm/vs/editor/editor.worker?worker'),
     import('monaco-editor/esm/vs/language/typescript/ts.worker?worker'),
     import('monaco-editor/esm/vs/language/json/json.worker?worker'),
     import('monaco-editor/esm/vs/language/html/html.worker?worker'),
     import('monaco-editor/esm/vs/language/css/css.worker?worker'),
     import('monaco-editor')
    ]);
    if (disposed) return;
    (globalThis as typeof globalThis & { MonacoEnvironment: unknown }).MonacoEnvironment = {
     getWorker: (_: string, label: string) => label === 'typescript' || label === 'javascript' ? new TsWorker() : label === 'json' ? new JsonWorker() : label === 'html' ? new HtmlWorker() : ['css','scss','less'].includes(label) ? new CssWorker() : new Worker()
    };
    const language = languages[filename.split('.').pop() || ''] || 'plaintext';
    before = monaco.editor.createModel(original, language);
    after = monaco.editor.createModel(modified, language);
    editor = monaco.editor.createDiffEditor(container, {
     theme: document.documentElement.classList.contains('dark') ? 'vs-dark' : 'vs',
     readOnly: true, originalEditable: false, renderSideBySide: false,
     automaticLayout: true, minimap: { enabled: false }, fontSize: 13,
     scrollBeyondLastLine: false, diffWordWrap: 'on', padding: { top: 12 },
     renderMarginRevertIcon: false,
     diffAlgorithm: 'advanced', ignoreTrimWhitespace: false,
     hideUnchangedRegions: { enabled: true, contextLineCount: 2, minimumLineCount: 4, revealLineCount: 5 }
    });
    editor.setModel({ original: before, modified: after });
    ready=true;
    themeObserver = new MutationObserver(() => monaco.editor.setTheme(document.documentElement.classList.contains('dark') ? 'vs-dark' : 'vs'));
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
   } catch (error) { failure = String(error); }
  })();
  return () => {
   disposed = true;
   ready = false;
   themeObserver?.disconnect();
   // Detach the diff view model while both text models are still alive so its
   // outstanding worker calculation is canceled before their disposal.
   editor?.setModel(null);
   editor?.dispose();
   before?.dispose();
   after?.dispose();
   editor = undefined;
   before = undefined;
   after = undefined;
  };
 });
 $effect(()=>{const oldText=original,newText=modified;if(ready&&before&&after){if(before.getValue()!==oldText)before.setValue(oldText);if(after.getValue()!==newText)after.setValue(newText);}});
</script>

<div class="source-diff" bind:this={container} aria-label="Inline code changes"></div>
{#if failure}<p role="alert">Review could not load: {failure}</p><pre>{modified}</pre>{/if}
<style>.source-diff{height:100%;min-height:320px;min-width:0}pre{white-space:pre-wrap}:global(.source-diff .line-insert){background:color-mix(in srgb,#3fb981 16%,transparent)!important}:global(.source-diff .line-delete){background:color-mix(in srgb,#ef6b73 16%,transparent)!important}</style>
