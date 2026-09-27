<script lang="ts">
 import { onMount } from 'svelte';
 import type * as Monaco from 'monaco-editor';

 let { original, modified, filename }: { original: string; modified: string; filename: string } = $props();
 let container: HTMLDivElement;
 let failure = $state('');
 const languages: Record<string, string> = {py:'python',js:'javascript',mjs:'javascript',ts:'typescript',tsx:'typescript',jsx:'javascript',java:'java',c:'c',h:'c',cpp:'cpp',cc:'cpp',go:'go',rs:'rust',php:'php',rb:'ruby',html:'html',css:'css',json:'json',md:'markdown',sh:'shell',sql:'sql',yaml:'yaml',yml:'yaml'};

 onMount(() => {
  let disposed = false;
  let editor: Monaco.editor.IStandaloneDiffEditor | undefined;
  let before: Monaco.editor.ITextModel | undefined;
  let after: Monaco.editor.ITextModel | undefined;
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
     diffAlgorithm: 'advanced', ignoreTrimWhitespace: true,
     hideUnchangedRegions: { enabled: true, contextLineCount: 2, minimumLineCount: 4, revealLineCount: 5 }
    });
    editor.setModel({ original: before, modified: after });
   } catch (error) { failure = String(error); }
  })();
  return () => { disposed = true; editor?.dispose(); before?.dispose(); after?.dispose(); };
 });
</script>

<div class="source-diff" bind:this={container} aria-label="Inline code changes"></div>
{#if failure}<p role="alert">Review could not load: {failure}</p><pre>{modified}</pre>{/if}
<style>.source-diff{height:100%;min-height:320px;min-width:0}pre{white-space:pre-wrap}</style>
