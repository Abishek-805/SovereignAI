<script lang="ts">
	import './knowledge-workspace.css';
	import { onMount, tick } from 'svelte';
	import FileText from '@lucide/svelte/icons/file-text';
	import Upload from '@lucide/svelte/icons/upload';
	import Search from '@lucide/svelte/icons/search';
	import FolderOpen from '@lucide/svelte/icons/folder-open';
	import Eye from '@lucide/svelte/icons/eye';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import * as Dialog from '$lib/components/ui/dialog';
	import {
		KnowledgeService,
		knowledgeJson,
		type KnowledgeDocument
	} from '$lib/services/knowledge.service';
	type Content = KnowledgeDocument & {
		pages: number[];
		methods: string[];
		text: string;
		original_url: string | null;
		passages?: { chunk_id: string; page: number | null; text: string }[];
	};
	let { target }: { target?: { id: string; page?: number | null; chunk?: string } } = $props();
	$effect(() => {
		if (target) void open(target.id, target.page, target.chunk);
	});
	let docs = $state<KnowledgeDocument[]>([]),
		active = $state<Content | null>(null),
		filter = $state(''),
		folderFilter = $state('');
	let loading = $state(true),
		importing = $state(false),
		opening = $state(false),
		notice = $state(''),
		error = $state(''),
		view = $state('original'),
		page = $state(1),
		evidenceChunk = $state(''),
		listVisible = $state(true);
	let libraryWidth=$state(280), libraryResizing=$state(false);
 let libraryGrid: HTMLDivElement;
 function resizeLibrary(event:PointerEvent){if(event.button!==0)return;event.preventDefault();event.currentTarget instanceof HTMLElement&&event.currentTarget.setPointerCapture(event.pointerId);libraryResizing=true;}
 function moveLibrary(event:PointerEvent){if(!libraryResizing)return;libraryWidth=Math.max(200,Math.min(460,Math.floor(libraryGrid.clientWidth*.45),event.clientX-libraryGrid.getBoundingClientRect().left));}
 function finishLibrary(){libraryResizing=false;try{localStorage.setItem('sovereign-knowledge-library-width',String(libraryWidth));}catch{}}
 let importMenu: HTMLDetailsElement;
	let filesInput: HTMLInputElement, folderInput: HTMLInputElement;
	let managing = $state(false),
		actionError = $state('');
	let action = $state<'rename' | 'move' | 'remove' | null>(null),
		name = $state(''),
		folder = $state('');
	let requestSequence = 0;
	const visible = $derived(
		docs.filter(
			(doc) =>
				(doc.display_name + ' ' + (doc.folder || ''))
					.toLowerCase()
					.includes(filter.toLowerCase()) &&
				(!folderFilter || doc.folder === folderFilter)
		)
	);
	const libraryFolders = $derived(
		[...new Set(docs.map((doc) => doc.folder || '').filter(Boolean))].sort()
	);
	const isPdf = $derived(
		!!active &&
			(active.source_extension || '.' + active.display_name.split('.').at(-1)?.toLowerCase()) ===
				'.pdf'
	);
	async function refresh() {
		loading = true;
		error = '';
		try {
			docs = await KnowledgeService.list();
			if (active && !docs.some((doc) => doc.document_id === active!.document_id)) active = null;
		} catch (e) {
			error = String(e);
		} finally {
			loading = false;
		}
	}
	async function open(id: string, location?: number | null, chunk?: string) {
		const sequence = ++requestSequence;
		opening = true;
		error = '';
		try {
			const content = await knowledgeJson(await fetch(`/documents/${id}/content`));
			if (sequence !== requestSequence) return;
			active = content;
			page = location || content.pages[0] || 1;
			evidenceChunk = chunk || '';
			view = chunk ? 'text' : 'original';
			folder = content.folder || '';
			sessionStorage.setItem('sovereign-knowledge-active', id);
			if (window.innerWidth < 700) listVisible = false;
			await tick();
			if (chunk) document.getElementById('passage-' + chunk)?.scrollIntoView({ block: 'center' });
		} catch (e) {
			if (sequence === requestSequence) error = String(e);
		} finally {
			if (sequence === requestSequence) opening = false;
		}
	}
	let dropping = $state(false);
	let importJob = $state('');
	async function stopImport() {
		try {
			if (importJob) await knowledgeJson(await fetch(`/coding/jobs/${importJob}/stop`, { method: 'POST', signal: AbortSignal.timeout(15000) }));
		} catch (e) { error = String(e); }
	}
	const supportedExtensions = '.pdf,.docx,.xlsx,.pptx,.txt,.md,.markdown,.csv,.tsv,.json,.jsonl,.log,.xml,.html,.htm,.css,.yaml,.yml,.toml,.ini,.cfg,.sql,.py,.js,.jsx,.ts,.tsx,.java,.c,.cpp,.h,.cs,.go,.rs,.php,.rb,.sh,.ps1,.tex';
	async function upload(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		await importFiles(Array.from(input.files || []));
		input.value = '';
	}
	async function importFiles(selected: File[], paths: Map<File, string> = new Map()) {
		if (importing || managing) return;
		const files = selected.filter((file) =>
			supportedExtensions.split(',').includes('.' + file.name.split('.').at(-1)?.toLowerCase())
		);
		if (!files.length) {
			notice = 'No supported documents selected.';
			return;
		}
		importing = true;
		error = '';
		let count = 0;
		try {
			for (const file of files) {
				notice = 'Importing and indexing ' + file.name + '…';
				const data = new FormData();
				data.append('file', file, file.name.split(/[\\/]/).at(-1) || file.name);
				let added = await knowledgeJson(
					await fetch('/documents/import?background=true', { method: 'POST', body: data, signal: AbortSignal.timeout(180000) })
				);
				importJob = added.job_id;
				while (added.state === 'running') {
					notice = `${file.name}: ${added.stage} (${added.elapsed}s)`;
					await new Promise((resolve) => setTimeout(resolve, 500));
					added = await knowledgeJson(await fetch(`/coding/jobs/${importJob}`, { signal: AbortSignal.timeout(15000) }));
				}
				importJob = '';
				if (added.state !== 'completed') throw new Error(added.error || 'Document import stopped before indexing completed.');
				added = added.result;
				const relativePath = paths.get(file) || file.webkitRelativePath;
				if (relativePath)
					await knowledgeJson(
						await fetch(`/documents/${added.document_id}/move`, {
							method: 'POST',
							headers: { 'content-type': 'application/json' },
							body: JSON.stringify({
								folder: relativePath.split('/').slice(0, -1).join('/'),
								expected_hash: added.active_hash
							})
						})
					);
				count++;
			}
			await refresh();
			notice = `${count} document${count === 1 ? '' : 's'} indexed.`;
		} catch (e) {
			error = e instanceof DOMException && e.name === 'TimeoutError'
				? 'The import connection timed out. The server may still be indexing. Refresh the library to check before importing again.'
				: String(e);
			notice = count ? `${count} documents imported before the error.` : '';
		} finally {
			importJob = '';
			importing = false;
		}
	}
	async function dropFiles(event: DragEvent) {
		event.preventDefault();
		dropping = false;
		if (importing || managing || !event.dataTransfer) return;
		const collected: File[] = [],
			paths = new Map<File, string>();
		async function walk(entry: FileSystemEntry, path = '') {
			if (collected.length >= 1000) throw new Error('Drop up to 1000 files at a time.');
			const location = path + entry.name;
			if (entry.isFile) {
				const file = await new Promise<File>((resolve, reject) =>
					(entry as FileSystemFileEntry).file(resolve, reject)
				);
				collected.push(file);
				paths.set(file, location);
			} else if (entry.isDirectory) {
				const reader = (entry as FileSystemDirectoryEntry).createReader();
				while (true) {
					const entries = await new Promise<FileSystemEntry[]>((resolve, reject) =>
						reader.readEntries(resolve, reject)
					);
					if (!entries.length) break;
					for (const child of entries) await walk(child, location + '/');
				}
			}
		}
		try {
			for (const item of Array.from(event.dataTransfer.items)) {
				const entry = item.webkitGetAsEntry?.();
				if (entry) await walk(entry);
				else {
					const file = item.getAsFile();
					if (file) collected.push(file);
				}
			}
			await importFiles(collected, paths);
		} catch (e) {
			error = String(e);
		}
	}
	async function dropDocument(event: DragEvent, destination: string) {
		const id = event.dataTransfer?.getData('application/x-sovereign-document');
		if (!id) return;
		event.preventDefault();
		event.stopPropagation();
		dropping = false;
		const selected = docs.find((doc) => doc.document_id === id);
		if (!selected || importing || managing) return;
		managing = true;
		error = '';
		try {
			await knowledgeJson(
				await fetch('/documents/' + id + (event.ctrlKey || event.metaKey ? '/copy' : '/move'), {
					method: 'POST',
					headers: { 'content-type': 'application/json' },
					body: JSON.stringify({ folder: destination, expected_hash: selected.active_hash })
				})
			);
			await refresh();
			if (active?.document_id === id) await open(id);
			notice =
				(event.ctrlKey || event.metaKey ? 'Copied to ' : 'Moved to ') +
				(destination || 'All documents') +
				'.';
		} catch (e) {
			error = String(e);
		} finally {
			managing = false;
		}
	}
	async function copyDocument() {
		if (!active || importing || managing) return;
		managing = true;
		error = '';
		try {
			const added = await knowledgeJson(
				await fetch('/documents/' + active.document_id + '/copy', {
					method: 'POST',
					headers: { 'content-type': 'application/json' },
					body: JSON.stringify({ expected_hash: active.active_hash })
				})
			);
			await refresh();
			await open(added.document_id);
			notice = 'Document copied. Source snapshots and indexed passages were reused.';
		} catch (e) {
			error = String(e);
		} finally {
			managing = false;
		}
	}
	function manage(next: 'rename' | 'move' | 'remove') {
		if (!active || importing || managing) return;
		actionError = '';
		name = active.display_name;
		folder = active.folder || '';
		action = next;
	}
	async function confirm() {
		if (!active || !action || managing) return;
		const selected = active,
			next = action;
		managing = true;
		actionError = '';
		try {
			const response = await knowledgeJson(
				await fetch(
					'/documents/' +
						selected.document_id +
						(next === 'move'
							? '/move'
							: next === 'remove'
								? '?expected_hash=' + encodeURIComponent(selected.active_hash || '')
								: ''),
					{
						method: next === 'rename' ? 'PATCH' : next === 'move' ? 'POST' : 'DELETE',
						headers: next === 'remove' ? undefined : { 'content-type': 'application/json' },
						body:
							next === 'remove'
								? undefined
								: JSON.stringify({
										...(next === 'rename'
											? { display_name: name.trim() }
											: { folder: folder.trim() }),
										expected_hash: selected.active_hash
									})
					}
				)
			);
			if (next === 'remove') active = null;
			else active = { ...selected, ...response };
			notice =
				next === 'remove'
					? 'Deleted from the library and index. Original files on your computer are unchanged.'
					: next === 'move'
						? 'Moved to library folder ' + (response.folder || 'All documents') + '.'
						: 'Document renamed.';
			action = null;
			await refresh();
		} catch (e) {
			actionError = String(e);
		} finally {
			managing = false;
		}
	}
	function useIn(target: 'chat' | 'agent') {
		if (active)
			KnowledgeService.connect(target, [{ id: active.document_id, name: active.display_name }]);
	}
	onMount(() => {
  const width=Number(localStorage.getItem('sovereign-knowledge-library-width'));if(width>=200&&width<=460)libraryWidth=width;
		const closeImportMenu = (event: KeyboardEvent) => {
			if (event.key !== 'Escape' || !importMenu?.open) return;
			event.preventDefault();
			event.stopPropagation();
			importMenu.open = false;
			importMenu.querySelector('summary')?.focus();
		};
		window.addEventListener('keydown', closeImportMenu, true);
		void refresh().then(() => {
			const id = sessionStorage.getItem('sovereign-knowledge-active');
			if (!target && id && docs.some((doc) => doc.document_id === id)) void open(id);
		});
		return () => window.removeEventListener('keydown', closeImportMenu, true);
	});
</script>

<svelte:window
	onclick={(event) => {
		if (importMenu?.open && !importMenu.contains(event.target as Node)) importMenu.open = false;
	}}
/>
<section
	class="documents knowledge-library"
	class:knowledge-dropping={dropping}
	aria-label="Knowledge library"
	ondragover={(event) => {
		if (event.dataTransfer?.types.includes('Files')) {
			event.preventDefault();
			dropping = true;
		}
	}}
	ondragleave={(event) => {
		if (!event.currentTarget.contains(event.relatedTarget as Node)) dropping = false;
	}}
	ondrop={dropFiles}
>
	{#if dropping}<div class="knowledge-drop-hint">
			Drop files or a folder to import into Knowledge
		</div>{/if}
	<header class="knowledge-library-head">
		<div>
			<span class="eyebrow">LOCAL LIBRARY</span>
			<h1>Knowledge</h1>
			<p>Store, find, and inspect your documents.</p>
		</div>
		<div>
			<button title="Refresh library" aria-label="Refresh Knowledge" onclick={refresh}
				><RefreshCw size={16} /></button
			>
			{#if importJob}<button onclick={stopImport}>Stop import</button>{/if}
			<details class="knowledge-import-menu" bind:this={importMenu}>
				<summary class="knowledge-add"
					><Upload size={15} /> {importing ? 'Indexing…' : 'Add documents'}</summary
				>
				<div class="knowledge-import-options">
					<button
						disabled={importing}
						onclick={() => {
							importMenu.open = false;
							filesInput.click();
						}}>Upload files</button
					><button
						disabled={importing}
						onclick={() => {
							importMenu.open = false;
							folderInput.click();
						}}><FolderOpen size={14} /> Import folder</button
					>
					<p>PDF, Word, Excel, PowerPoint and text · up to 20 MB each</p>
				</div>
			</details>
			<input
				bind:this={filesInput}
				type="file"
				multiple
				accept={supportedExtensions}
				onchange={upload}
				disabled={importing}
			/>
			<input
				bind:this={folderInput}
				type="file"
				multiple
				webkitdirectory={true}
				onchange={upload}
				disabled={importing}
			/>
		</div>
	</header>
	{#if notice || error}<div class="knowledge-library-notice" role={error ? 'alert' : 'status'}>
			{error || notice}{#if error}<button onclick={refresh}>Retry</button>{/if}
		</div>{/if}
	<div class="knowledge-library-grid" class:list-hidden={!listVisible} bind:this={libraryGrid} style:--library-width={libraryWidth+'px'}>
		<aside class="knowledge-list">
			<div class="context-search">
				<Search size={16} /><input
					aria-label="Search documents"
					bind:value={filter}
					placeholder="Search your library…"
				/>
			</div>
			{#if libraryFolders.length}<label class="knowledge-folder-filter"
				>Folder<select aria-label="Filter library folder" bind:value={folderFilter}
					><option value="">All documents</option>{#each libraryFolders as item}<option value={item}
							>{item}</option
						>{/each}</select
				></label
			>
			{/if}<div class="knowledge-folder-targets" aria-label="Library folders">
				<button
					class:active={!folderFilter}
					onclick={() => (folderFilter = '')}
					ondragover={(event) => {
						if (event.dataTransfer?.types.includes('application/x-sovereign-document'))
							event.preventDefault();
					}}
					ondrop={(event) => void dropDocument(event, '')}>All documents</button
				>{#each libraryFolders as destination}<button
						class:active={folderFilter === destination}
						onclick={() => (folderFilter = destination)}
						title={'Drop to move to ' + destination + '; hold Ctrl to copy'}
						ondragover={(event) => {
							if (event.dataTransfer?.types.includes('application/x-sovereign-document'))
								event.preventDefault();
						}}
						ondrop={(event) => void dropDocument(event, destination)}>{destination}</button
					>{/each}
			</div>
			<div class="knowledge-list-heading"><strong>Documents</strong><span>{docs.length}</span></div>
			<div class="knowledge-files">
				{#if loading}<p role="status">Reading your library…</p>{:else}{#each visible as doc}<button
							class:active={active?.document_id === doc.document_id}
							aria-current={active?.document_id === doc.document_id ? 'true' : undefined}
							onclick={() => open(doc.document_id)}
							title={doc.display_name}
							draggable={true}
							ondragstart={(event) => {
								event.dataTransfer?.setData('application/x-sovereign-document', doc.document_id);
							}}
							><FileText size={18} /><span
								><strong>{doc.display_name}</strong><small
									>{(
										doc.source_extension?.slice(1) || doc.display_name.split('.').at(-1)
									)?.toUpperCase()} · {doc.chunk_count} passages · Indexed</small
								>{#if doc.folder}<small>{doc.folder}</small>{/if}</span
							></button
						>{/each}{#if !visible.length}<p>
							{docs.length
								? 'No matching documents.'
								: 'No documents yet. Add local files to start your library.'}
						</p>{/if}{/if}
			</div>
		</aside>
  <!-- Keyboard-adjustable separator follows the ARIA window splitter pattern. -->
  <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
  <div class="knowledge-library-resizer" role="separator" aria-label="Resize document library" aria-orientation="vertical" aria-valuemin={200} aria-valuemax={460} aria-valuenow={libraryWidth} tabindex="0" onpointerdown={resizeLibrary} onpointermove={moveLibrary} onpointerup={finishLibrary} onpointercancel={finishLibrary} onkeydown={(event)=>{if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();libraryWidth=Math.max(200,Math.min(460,libraryWidth+(event.key==='ArrowRight'?20:-20)));finishLibrary();}}}></div>
		<main class="knowledge-preview">
			<div class="knowledge-preview-head">
				<div>
					<button
						class="knowledge-list-toggle"
						aria-pressed={listVisible}
						onclick={() => (listVisible = !listVisible)}>Documents</button
					>
					<h2>{active?.display_name || 'Document preview'}</h2>
				</div>
				{#if active}<div class="knowledge-preview-actions">
						<button aria-pressed={view === 'original'} onclick={() => (view = 'original')}
							><Eye size={14} /> Preview</button
						><button aria-pressed={view === 'text'} onclick={() => (view = 'text')}
							>Extracted text</button
						>
      <details class="knowledge-file-actions"><summary>Manage</summary><div class="knowledge-file-actions-menu"><button disabled={importing || managing} onclick={() => manage('rename')}>Rename</button><button disabled={importing || managing} onclick={() => manage('move')}>Move</button><button disabled={importing || managing} onclick={copyDocument}>Copy</button><button disabled={importing || managing} onclick={() => manage('remove')}>Delete</button></div></details>
						<details>
							<summary>Use as context</summary><button onclick={() => useIn('chat')}
								>Connect to Chat</button
							><button onclick={() => useIn('agent')}>Connect to Agent</button>
						</details>
					</div>{/if}
			</div>

			<div class="knowledge-preview-body">
				{#if opening}<p role="status">
						Opening document…
					</p>{:else if active}{#if view === 'original' && isPdf && active.original_url}<iframe
							title={'Preview ' + active.display_name}
							src={active.original_url + '#page=' + page}
						></iframe>{:else if view === 'original' && !isPdf}<article class="knowledge-paper">
							<span class="eyebrow">EXTRACTED PREVIEW</span>
							<p class="knowledge-preview-note">
								{active.display_name.endsWith('.docx')
									? 'Original Word layout is available by downloading the file.'
									: 'Text extracted from your original file.'}
							</p>
							<pre>{active.text}</pre>
						</article>{:else}<article class="knowledge-paper">
							<span class="eyebrow">INDEXED PASSAGES</span
							>{#each active.passages || [] as passage}<section
									id={'passage-' + passage.chunk_id}
									class:highlighted={evidenceChunk === passage.chunk_id}
								>
									<small>{passage.page ? `Page ${passage.page}` : 'Text passage'}</small>
									<pre>{passage.text}</pre>
								</section>{/each}{#if !active.passages?.length}<pre>{active.text}</pre>{/if}
						</article>{/if}{:else}<div class="knowledge-library-empty">
						<FileText size={32} />
						<h2>Your documents, in one place.</h2>
						<p>
							Select a document to preview its original file and inspect indexed passages. Connect
							it to Chat or Agent when you need an answer or a task.
						</p>
					</div>{/if}
			</div>
			{#if active}<footer class="knowledge-file-info">
					<div>
						<span
							>{active.pages.length
								? `${active.pages.length} indexed pages`
								: 'Text document'}</span
						><span>{active.chunk_count} passages</span><span
							>{active.methods.join(', ').replaceAll('_', ' ')}</span
						>{#if active.active_hash}<span title={active.active_hash}
								>Version {active.active_hash.slice(0, 8)}</span
							>{/if}
					</div>
					<div>
						{#if isPdf}<label
								>Page <select aria-label="Preview page" bind:value={page}
									>{#each active.pages as pageNumber}<option value={pageNumber}>{pageNumber}</option
										>{/each}</select
								></label
							>{/if}{#if active.original_url}<a
								href={active.original_url}
								target="_blank"
								rel="noreferrer">Original ↗</a
							>{/if}
						<details>
							<summary>File info</summary>
							<p>
								Connected context grants read access only. Updates retain the same document ID and
								preserve earlier source snapshots.
							</p>
							{#each active.warnings || [] as warning}<p>{warning}</p>{/each}
						</details>
					</div>
				</footer>{/if}
		</main>
	</div>
</section>
<Dialog.Root
	open={!!action}
	onOpenChange={(value) => {
		if (!value) action = null;
	}}
	><Dialog.Content class="knowledge-management-dialog"
		><Dialog.Header
			><Dialog.Title
				>{action === 'rename'
					? 'Rename document'
					: action === 'move'
						? 'Move document'
						: 'Delete from library?'}</Dialog.Title
			><Dialog.Description
				>{active?.display_name}. {action === 'remove'
					? 'This removes all indexed versions and citations from the library. Original files and stored source snapshots remain on disk.'
					: action === 'move'
						? 'Organize within the Knowledge library; original files are not moved on your computer.'
						: ''}</Dialog.Description
			></Dialog.Header
		>
		<form
			onsubmit={(event) => {
				event.preventDefault();
				void confirm();
			}}
		>
			{#if action === 'rename'}<input
					aria-label="New document name"
					bind:value={name}
					required
					maxlength="255"
				/>{:else if action === 'move'}<label
					>Library folder<input
						aria-label="Destination library folder"
						bind:value={folder}
						maxlength="240"
						placeholder="e.g. Projects/Inspection"
						list="library-folders"
					/></label
				><datalist id="library-folders"
					>{#each libraryFolders as item}<option value={item}></option>{/each}</datalist
				>
				<p class="knowledge-dialog-hint">
					Leave empty to return to All documents.
				</p>{/if}{#if actionError}<p role="alert">{actionError}</p>{/if}<Dialog.Footer
				><button type="button" class="context-secondary" onclick={() => (action = null)}
					>Cancel</button
				><button class="context-primary" type="submit" disabled={managing}
					>{managing
						? 'Saving…'
						: action === 'rename'
							? 'Rename'
							: action === 'move'
								? 'Move'
								: 'Delete'}</button
				></Dialog.Footer
			>
		</form></Dialog.Content
	></Dialog.Root
>
