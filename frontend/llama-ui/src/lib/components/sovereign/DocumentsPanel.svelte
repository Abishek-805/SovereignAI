<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { chatStore, conversationsStore, uiStore } from '$lib/stores';
	import DockerControl from './DockerControl.svelte';
	import { ArrowLeft, Bot, Code2, Cpu, FileText, FolderDown, MessageSquare, Download, RefreshCw, Table2, Presentation, FileCode2, CheckCircle2, AlertCircle, Trash2 } from '@lucide/svelte';
	import { setMode } from 'mode-watcher';
 import CodingWorkspacePanel from './CodingWorkspacePanel.svelte';
 import AgentChat from './AgentChat.svelte';
 import DocumentLibrary from './DocumentLibrary.svelte';
	import TaskTimeline from './TaskTimeline.svelte';
	import type { AgentResult } from '$lib/services/agent-contract';
	import { WorkbenchService, type ArtifactEntry, type WorkbenchInfo } from '$lib/services/workbench.service';

	type Document = { document_id: string; display_name: string; chunk_count: number; active_hash: string };
	type Source = { label: string; chunk_id: string; display_name: string; page: number | null; text: string };
	type SourceDetail = Source & { document_id: string; version_hash: string; line_start: number | null; line_end: number | null; extraction_method: string; original_url: string };
	let open = $state(false);
	let agentMode = $state('documents');
	let documents = $state<Document[]>([]);
	let selected = $state<string[]>([]);
	let question = $state('');
	let answer = $state('');
	let answerStatus = $state('');
	let sources = $state<Source[]>([]);
	let sourceDetails = $state<Record<string, SourceDetail>>({});
	let sourceErrors = $state<Record<string, string>>({});
	let activeSourceId = $state('');
	let loadingSourceId = $state('');
	let message = $state('');
	let busy = $state(false);
	let downloads = $state<{ word: string; excel: string; slides: string } | null>(null);
	let imageQuestion = $state('');
	let imageFile = $state<File | null>(null);
	let imageAnswer = $state('');
	let visionController: AbortController | null = null;
	let codingResult = $state<{ status: string; task_id: string; checks: Record<string, boolean>; attempts: number; code?: string; message?: string } | null>(null);
	let agentGoal = $state('');
	let agentTrace = $state('');
	let agentResult = $state<AgentResult | null>(null);
	let agentWorkspace = $state('');
	let agentTarget = $state('');
	let workspaces = $state<{ workspace_id: string; name: string }[]>([]);
	let agentImage = $state<File | null>(null);
	let calculationText = $state('');
	let workbenchInfo = $state<WorkbenchInfo | null>(null);
	let runtimeLoading = $state(false);
	let runtimeError = $state('');
	let artifacts = $state<ArtifactEntry[]>([]);
	let deletingArtifact = $state<ArtifactEntry | null>(null);
	const orderedArtifacts = $derived([...artifacts].sort((a, b) => artifactEpoch(b.created_at) - artifactEpoch(a.created_at)));
	let agentFailure = $state<{ code: string; message: string; task_id?: string } | null>(null);
	let agentTask = $state<{ task_id: string; state: string; agent_state?: string; agent_history?: AgentResult['tool_results']; agent_result?: Partial<AgentResult>; error_code?: string; checks?: Record<string, boolean> } | null>(null);
	let taskLookup = $state('');
	type PanelTab = 'knowledge' | 'workflows' | 'vision' | 'code' | 'agent' | 'artifacts' | 'runtime';
	let activeTab = $state<PanelTab>('knowledge');
	let tabHistory = $state<PanelTab[]>([]);
	let controlSection = $state<'models' | 'knowledge' | 'runtime' | 'system' | 'appearance'>('models');
	let visited = $state<PanelTab[]>([]);
	let runningView = $state('');
	let runningStage = $state('');
	let runningJobId = $state('');
	async function stopRunningJob(){if(!runningJobId)return;runningStage='Stopping after the current step…';await fetch('/coding/jobs/'+runningJobId+'/stop',{method:'POST'});}
	function workbenchKeys(event: KeyboardEvent) {
		if (event.ctrlKey && event.altKey && !event.shiftKey && /^[1-7]$/.test(event.key)) {
			event.preventDefault();
			const destination: PanelTab[] = ['knowledge', 'agent', 'code', 'artifacts', 'runtime'];
			if (event.key === '1') closePanel();
			else if (event.key === '7') { controlSection = 'runtime'; openTab('runtime'); }
			else openTab(destination[Number(event.key) - 2]);
			return;
		}
		if (open && event.key === 'Escape' && !document.body.classList.contains('sovereign-code-focus') && !document.querySelector('[aria-label="Select project"], [aria-label="File actions"], [aria-label="Rename file"], [aria-label="Delete file"], .shortcut-dialog, .manage-dialog, .document-action-dialog, .palette, .ide-menu-pop')) {
			event.preventDefault(); closePanel();
		}
	}

	onMount(() => {
		const handleOpen = (event: Event) => {
			const detail = (event as CustomEvent<{ tab?: PanelTab; draft?: string }>).detail;
			if (detail?.draft && detail.tab === 'agent') {
				agentGoal = detail.draft.slice(0, 2000);
				if (/^calculate:/i.test(agentGoal.trim())) agentMode = 'calculate';
			}
			openTab(detail?.tab || 'agent');
		};
		window.addEventListener('sovereign-open-workspace', handleOpen);
		const handleActivity = (event: Event) => {
			const detail = (event as CustomEvent<{view:string;stage:string;running:boolean;jobId?:string}>).detail;
			runningView = detail.running ? detail.view : '';
			runningStage = detail.running ? detail.stage : '';
			runningJobId = detail.running ? detail.jobId || '' : '';
		};
		window.addEventListener('sovereign-activity', handleActivity);
		const close = () => { open = false; tabHistory = []; };
		window.addEventListener('sovereign-close-workspace', close);
		return () => { window.removeEventListener('sovereign-open-workspace', handleOpen); window.removeEventListener('sovereign-activity', handleActivity); window.removeEventListener('sovereign-close-workspace', close); };
	});

	function userError(error: unknown) {
		return error instanceof TypeError
			? 'Local workbench disconnected. Start SovereignAI, then retry the connection.'
			: String(error);
	}

	async function readJson(response: Response) {
		const body = await response.json();
		if (!response.ok) throw new Error((body.message || `Request failed (${response.status})`) + (body.task_id ? ` · task ${body.task_id}` : ''));
		return body;
	}

	async function refresh() {
		if (activeTab === 'runtime') { runtimeLoading = true; runtimeError = ''; }
		try {
			documents = await readJson(await fetch('/documents'));
			workspaces = await readJson(await fetch('/coding/workspaces'));
			if (activeTab === 'runtime' || activeTab === 'code' || activeTab === 'agent') workbenchInfo = await WorkbenchService.info();
			if (activeTab === 'artifacts') artifacts = await WorkbenchService.artifacts();
			selected = selected.filter((id) => documents.some((doc) => doc.document_id === id));
		} catch (error) {
			message = userError(error);
			if (activeTab === 'runtime') { runtimeError = message; workbenchInfo = null; }
		} finally {
			runtimeLoading = false;
		}
	}

	async function deleteArtifact() {
		if (!deletingArtifact) return;
		const target = deletingArtifact;
		try {
			await WorkbenchService.deleteArtifact(target.task_id, target.name);
			artifacts = artifacts.filter(item => item.task_id !== target.task_id || item.name !== target.name);
			message = `${target.name} deleted from local downloads.`;
			deletingArtifact = null;
		} catch (error) { message = userError(error); }
	}

	function openTab(tab: PanelTab, remember = true) {
		if (remember && open && activeTab !== tab) tabHistory = [...tabHistory, activeTab];
		activeTab = tab;
		window.dispatchEvent(new CustomEvent('sovereign-workspace-selected', { detail: { tab } }));
		if (!visited.includes(tab)) visited = [...visited, tab];
        if(tab==='code')uiStore.isSidebarExpanded=false;
		open = true;
		void tick().then(() => (document.querySelector('#sovereign-documents h2') as HTMLElement)?.focus());
		void refresh();
	}

	function closePanel() {
		open = false;
		tabHistory = [];
		window.dispatchEvent(new Event('sovereign-close-workspace'));
		(document.querySelector('[aria-label="Agent"]') as HTMLButtonElement | null)?.focus();
	}

	function goBack() {
		const previous = tabHistory.at(-1);
		if (!previous) { closePanel(); return; }
		tabHistory = tabHistory.slice(0, -1);
		openTab(previous, false);
	}

	async function loadTask(id: string) {
		if (!/^[a-f0-9]{32}$/.test(id)) { message = 'Enter a 32-character task ID.'; return; }
		try { agentTask = await readJson(await fetch(`/tasks/${id}`)); message = ''; }
		catch (error) { message = userError(error); }
	}

	function toggleDocument(id: string) {
		selected = selected.includes(id) ? selected.filter((item) => item !== id) : [...selected, id];
	}

	function artifactTime(value: string | number | null): string {
		if (!value) return 'time unavailable';
		const parsed = new Date(typeof value === 'number' ? value * 1000 : value);
		return Number.isNaN(parsed.getTime()) ? 'time unavailable' : parsed.toLocaleString();
	}
	function artifactEpoch(value: string | number | null): number {
		if (!value) return 0;
		const parsed = typeof value === 'number' ? value * 1000 : Date.parse(value);
		return Number.isFinite(parsed) ? parsed : 0;
	}
	function artifactKind(kind: string): string {
		return ({ word: 'Word document', excel: 'Excel workbook', slides: 'PowerPoint slides', code_result: 'Code output' } as Record<string,string>)[kind] || 'File';
	}

	async function inspectSource(source: Source) {
		activeSourceId = source.chunk_id;
		if (sourceDetails[source.chunk_id] || loadingSourceId === source.chunk_id) return;
		loadingSourceId = source.chunk_id;
		try {
			const detail = await readJson(await fetch(`/sources/${source.chunk_id}`)) as SourceDetail;
			if (detail.chunk_id !== source.chunk_id || detail.text !== source.text) {
				throw new Error('Saved evidence differs from the answer passage. Do not rely on this citation.');
			}
			sourceDetails[source.chunk_id] = detail;
			delete sourceErrors[source.chunk_id];
		} catch (error) {
			sourceErrors[source.chunk_id] = String(error);
		} finally {
			loadingSourceId = '';
		}
	}

	async function upload(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const files = Array.from(input.files || []);
		if (!files.length) return;
		busy = true;
		message = `Importing ${files.length} file(s)…`;
		let imported = 0;
		try {
			for (const file of files) {
				const form = new FormData();
				form.append('file', file);
				await readJson(await fetch('/documents/import', { method: 'POST', body: form }));
				imported++;
			}
			message = `Imported ${files.length} file(s).`;
		} catch (error) {
			message = `${imported ? `Imported ${imported} file(s). ` : ''}${userError(error)}`;
		} finally {
			await refresh();
			busy = false;
			input.value = '';
		}
	}

	async function ask() {
		if (!question.trim() || busy) return;
		busy = true;
		message = 'Searching documents and checking the answer…';
		answer = '';
		answerStatus = '';
		sources = [];
		sourceDetails = {};
		sourceErrors = {};
		activeSourceId = '';
		try {
			const runtime = await readJson(await fetch('/status'));
			if (runtime.generator?.is_sleeping) message = 'Local model was sleeping; waking it to check this answer…';
			const result = await readJson(
				await fetch('/ask', {
					method: 'POST',
					headers: { 'content-type': 'application/json' },
					body: JSON.stringify({ question, document_ids: selected.length ? selected : null })
				})
			);
			answer = result.answer;
			answerStatus = result.status;
			sources = result.sources || [];
			message = result.status === 'answered' ? 'Answer linked to saved passages.'
				: result.status === 'citation_failure' ? 'Citation check failed. Review the passages before using this answer.'
				: result.status === 'insufficient_evidence' ? 'The selected documents do not establish this answer.'
				: result.status;
		} catch (error) {
			message = userError(error);
		} finally {
			busy = false;
		}
	}

	async function draft() {
		if (!selected.length || busy) return;
		busy = true;
		message = 'Checking evidence and creating draft files…';
		downloads = null;
		try {
			const result = await readJson(
				await fetch('/workflows/maintenance-draft', {
					method: 'POST',
					headers: { 'content-type': 'application/json' },
					body: JSON.stringify({ document_ids: selected })
				})
			);
			downloads = result.downloads;
			message = `Draft completed. ${result.findings?.length || 0} finding(s) checked.`;
		} catch (error) {
			message = userError(error);
		} finally {
			busy = false;
		}
	}

	async function askImage() {
		if (!imageFile || !imageQuestion.trim() || busy) return;
		busy = true;
		imageAnswer = '';
		message = 'Reading image with the vision model…';
		try {
			const form = new FormData();
			form.append('file', imageFile);
			form.append('question', imageQuestion);
			visionController = new AbortController();
			const result = await readJson(await fetch('/vision/ask', { method: 'POST', body: form, signal: visionController.signal }));
			imageAnswer = result.answer;
			message = 'Vision answer ready. Check it against the original image.';
		} catch (error) {
			message = error instanceof Error && error.name === 'AbortError' ? 'Image request stopped.' : userError(error);
		} finally {
			visionController = null;
			busy = false;
		}
	}

	async function runCodingDemo() {
		if (busy) return;
		busy = true;
		codingResult = null;
		message = 'Generating code and checking four cases in the isolated local container…';
		try {
			codingResult = await readJson(await fetch('/workflows/csv-coding-demo', { method: 'POST' }));
			message = codingResult?.status === 'completed'
				? `Coding demo passed after ${codingResult.attempts} attempt(s).`
				: codingResult?.message || 'Coding demo failed its checks.';
		} catch (error) {
			message = userError(error);
		} finally {
			busy = false;
		}
	}

	async function runAgent() {
		if (busy || !agentGoal.trim()) return;
		if (agentMode === 'documents' && !selected.length && !/^calculate:/i.test(agentGoal.trim())) {
			message = 'Choose at least one document above so the task knows which sources to use.';
			return;
		}
		if (agentMode === 'image' && !agentImage) { message = 'Attach an image before starting.'; return; }
		if (agentMode === 'code' && (!agentWorkspace || !agentTarget.trim())) { message = 'Choose a workspace and the Python file to edit.'; return; }
		if (agentMode === 'calculate' && !/^calculate:/i.test(agentGoal.trim())) agentGoal = 'Calculate: ' + agentGoal;
		busy = true;
		agentTrace = '';
		agentResult = null;
		agentTask = null;
		agentFailure = null;
		calculationText = '';
		downloads = null;
		message = 'Planning an approved local workflow and checking its output…';
		try {
			let response: Response;
			if (agentImage) {
				const form = new FormData();
				form.append('file', agentImage);
				form.append('question', agentGoal);
				response = await fetch('/agent/vision', { method: 'POST', body: form });
			} else {
				response = await fetch('/agent/tasks', {
					method: 'POST', headers: { 'content-type': 'application/json' },
					body: JSON.stringify({ goal: agentGoal, document_ids: selected,
						workspace_id: agentWorkspace || null, target: agentTarget || null })
				});
			}
			const body = await response.json();
			if (!response.ok) {
				agentFailure = { code: body.code || 'task_failed', message: body.message || 'Agent task failed', task_id: body.task_id };
				if (body.task_id) await loadTask(body.task_id);
				throw new Error(agentFailure.message);
			}
			const run = body as AgentResult;
			agentResult = run;
			await loadTask(run.task_id);
			agentTrace = `Task ${run.task_id} · ${run.capability} · ${run.selected_model || 'no model'}`;
			if (run.workflow === 'maintenance_draft') downloads = run.result.downloads || null;
			if (run.workflow === 'calculate') calculationText = `${run.result.expression} = ${run.result.rounded}\n${(run.result.steps || []).join('\n')}`;
			message = `Agent task ${run.status}.`;
		} catch (error) {
			message = userError(error);
		} finally {
			busy = false;
		}
	}
</script>

<svelte:window onresize={() => { if (open && window.innerWidth < 768) uiStore.isSidebarExpanded = false; }} onkeydown={workbenchKeys} />

{#if visited.length}
	<aside id="sovereign-documents" class="workbench-canvas" class:canvas-hidden={!open} style:--sidebar-space={uiStore.isSidebarExpanded ? '304px' : '64px'} aria-label="SovereignAI workbench" aria-hidden={!open}>
		<header class="workbench-header flex items-center justify-between border-b border-border px-4 py-3">
			<div class="workbench-header-start"><button class="workbench-back" onclick={goBack} aria-label="Go back" title={tabHistory.length ? 'Previous section' : 'Return to chat'}><ArrowLeft size={17} /></button><h2 tabindex="-1" class="font-semibold">SovereignAI <span class="text-muted-foreground">/ {activeTab === 'knowledge' || activeTab === 'workflows' || activeTab === 'vision' ? 'Knowledge' : activeTab === 'code' ? 'Code' : activeTab === 'agent' ? 'Agent' : activeTab === 'artifacts' ? 'Downloads' : 'Control Center'}</span></h2></div>
			{#if runningView}<div class="activity-controls"><button class="activity-chip" onclick={()=>openTab(runningView === 'Code' ? 'code' : runningView === 'Documents' ? 'knowledge' : 'agent')}><i></i>{runningView} · {runningStage}</button>{#if runningJobId}<button class="activity-stop" onclick={stopRunningJob}>Stop</button>{/if}</div>{/if}
			{#if chatStore.isLoading || chatStore.isStreaming()}<div class="activity-controls"><span class="activity-chip"><i></i>Chat · generating</span><button class="activity-stop" onclick={()=>void chatStore.stopGeneration()}>Stop</button></div>{/if}
		</header>

		<div class="workbench-content space-y-6 overflow-y-auto text-sm" class:code-view={activeTab === 'code'}>
			{#if visited.includes('knowledge') || visited.includes('workflows')}<div class:hidden-view={activeTab !== 'knowledge' && activeTab !== 'workflows'}><DocumentLibrary report={activeTab === 'workflows'}/></div>{/if}
			{#if visited.includes('agent')}<div class:hidden-view={activeTab !== 'agent'}><AgentChat draft={agentGoal}/></div>{/if}
			{#if activeTab === 'vision'}
			<form class="space-y-2 border-t border-border pt-3" onsubmit={(event) => { event.preventDefault(); void askImage(); }}>
				<h3 class="font-medium">Ask about an image</h3>
				<input aria-label="Select PNG or JPEG image" type="file" accept=".png,.jpg,.jpeg" disabled={busy} onchange={(event) => { imageFile = event.currentTarget.files?.[0] || null; }} />
				<input aria-label="Image question" class="w-full rounded-lg border border-border bg-background p-2" bind:value={imageQuestion} placeholder="What is visible in this image?" />
				<button class="rounded-lg border border-border px-3 py-2 disabled:opacity-50" disabled={busy || !imageFile || !imageQuestion.trim()}>Ask image</button>
				{#if busy}<button type="button" class="rounded-lg border border-border px-3 py-2" onclick={()=>{visionController?.abort();message='Image request stopped.';}}>Stop</button>{/if}
				{#if imageAnswer}<p class="whitespace-pre-wrap rounded-lg bg-muted p-3">{imageAnswer}</p>{/if}
			</form>
			{/if}
			{#if visited.includes('code')}<div class:hidden-view={activeTab !== 'code'}><CodingWorkspacePanel/></div>{/if}
			{#if activeTab === 'artifacts'}
			<section class="downloads-page" aria-label="Validated artifacts">
				<div class="downloads-heading"><div><span class="downloads-eyebrow">YOUR LOCAL FILES</span><h3>Downloads <span class="downloads-count">{orderedArtifacts.length}</span></h3><p>Reports and sandbox results, checked before download.</p></div><div class="downloads-toolbar"><button onclick={() => openTab('runtime')}>Control Center</button><button onclick={() => void refresh()} aria-label="Refresh downloads"><RefreshCw size={15}/> Refresh</button></div></div>
				{#if !orderedArtifacts.length}<div class="downloads-empty"><FileText size={28}/><h4>No files yet</h4><p>Create a document report or complete a coding task to find its output here.</p></div>{/if}
				<div class="downloads-grid">
				{#each orderedArtifacts as artifact (artifact.task_id + ':' + artifact.name)}
					<article class="download-card" class:invalid={!artifact.validated}>
						<div class="download-card-main"><span class="download-file-icon" class:word={artifact.kind==='word'} class:excel={artifact.kind==='excel'} class:slides={artifact.kind==='slides'}>{#if artifact.kind==='excel'}<Table2 size={19}/>{:else if artifact.kind==='slides'}<Presentation size={19}/>{:else if artifact.kind==='code_result'}<FileCode2 size={19}/>{:else}<FileText size={19}/>{/if}</span><div class="download-file-info"><strong title={artifact.name}>{artifact.name}</strong><span>{artifactKind(artifact.kind)} · {artifactTime(artifact.created_at)}</span></div></div>
						<div class="download-card-bottom"><span class="download-task" title={'Task '+artifact.task_id}>Task {artifact.task_id.slice(0,8)}</span><span class="download-validation" class:failed={!artifact.validated}>{#if artifact.validated}<CheckCircle2 size={13}/> Verified{:else}<AlertCircle size={13}/> Validation failed{/if}</span>{#if artifact.validated && artifact.url}<a class="download-action" href={artifact.url} download aria-label={'Download '+artifact.name}><Download size={14}/> Download</a>{/if}<button class="download-delete" aria-label={'Delete '+artifact.name} title="Delete local output" onclick={() => deletingArtifact = artifact}><Trash2 size={14}/> Delete</button></div>
					</article>
				{/each}
				</div>
			</section>
			{/if}
			{#if deletingArtifact}<div class="download-confirm-backdrop" role="presentation"><div class="download-confirm" role="dialog" aria-modal="true" aria-label="Delete download"><h3>Delete local output?</h3><p>{deletingArtifact.name} will be removed from this computer's saved outputs.</p><div><button onclick={() => deletingArtifact = null}>Cancel</button><button class="danger" onclick={() => void deleteArtifact()}>Delete file</button></div></div></div>{/if}
			{#if activeTab === 'runtime'}
			<section class="control-center" aria-label="Control Center">
				<div class="control-heading"><div><p class="control-eyebrow">SOVEREIGNAI / MANAGEMENT</p><h3>Control Center</h3><p>Manage models, downloads, and appearance.</p></div><button class="control-button" onclick={() => void refresh()}>Refresh status</button></div>
				<div class="control-layout"><nav aria-label="Control Center sections">
					{#each [{id:'models',label:'Models & routing'},{id:'runtime',label:'Runtimes'},{id:'system',label:'System & downloads'},{id:'appearance',label:'Appearance'}] as section}
						<button class:selected={controlSection===section.id} aria-current={controlSection===section.id?'page':undefined} onclick={() => controlSection=section.id as typeof controlSection}>{section.label}</button>
					{/each}
				</nav><div class="control-body">
					{#if !workbenchInfo}<div class="control-card" role="status"><h4>{runtimeLoading ? 'Loading local status…' : 'Local status unavailable'}</h4><p>{runtimeLoading ? 'Reading the model registry and Docker state.' : runtimeError || 'Start SovereignAI and refresh to inspect runtime state.'}</p></div>{:else}
					{#if controlSection === 'models'}
						<h4>Models & routing</h4><p class="control-muted">Greetings use no model. Document questions use retrieval and the text model; project edits use the text model and Docker checks. Vision requests use the vision model. A coding model will be enabled only after it improves validated tasks and total response time on this computer.</p>
						<div class="control-card"><span>Current model</span><strong>{workbenchInfo.runtime.generator.available ? workbenchInfo.runtime.generator.alias || 'Model name unavailable' : 'No model running'}</strong><p>{workbenchInfo.runtime.generator.available ? workbenchInfo.runtime.generator.is_sleeping ? 'Sleeping · wakes for the next request' : 'Loaded locally' : 'Stopped or unavailable'} · {workbenchInfo.runtime.busy ? 'Task running' : 'Idle'}</p></div>
						<div class="control-card"><span>Routing policy</span><strong>{workbenchInfo.routing?.mode === 'automatic' ? 'Automatic' : 'Unavailable'}</strong>{#each Object.entries(workbenchInfo.routing?.routes || {}) as [task, route]}<p>{task}: {route.model || 'No available model'}</p>{/each}</div>
						<div class="control-card"><span>Context window</span><strong>Start a fresh chat</strong><p>Local tokens are a per-conversation context limit, not a refillable quota. Starting a new chat clears the active prompt history while keeping earlier chats in History. Knowledge has its own New chat button.</p><button class="control-button" onclick={() => void conversationsStore.openNewChat()}>Reset chat tokens · New chat</button></div>
						<div class="control-grid">{#each workbenchInfo.models as model}<div class="control-card"><span>{model.capability.toUpperCase()}</span><strong>{model.model_id}</strong><p>{!model.enabled ? 'Disabled' : !model.assets_present ? 'Model files missing' : workbenchInfo.runtime.generator.available && workbenchInfo.runtime.generator.alias === model.alias ? workbenchInfo.runtime.generator.is_sleeping ? 'Sleeping' : 'Loaded' : 'Installed'} · {model.quantization} · {model.context.toLocaleString()} context</p><p>Observed GPU memory: {model.observed_gpu_mib === null ? 'Not measured' : `${model.observed_gpu_mib} MiB`}</p></div>{/each}</div>
						<button class="control-button" onclick={async()=>{try{const response=await fetch('/workbench/model/unload',{method:'POST'});const body=await response.json();message=body.message||body.status;await refresh();}catch(e){message=String(e);}}}>Free AI memory</button>
					{:else if controlSection === 'knowledge'}
						<h4>Knowledge</h4><p class="control-muted">{workbenchInfo.runtime.documents} indexed documents. Read files and inspect grounded answers in the document workspace.</p><button class="control-button" onclick={() => openTab('knowledge')}>Open document library</button>
					{:else if controlSection === 'runtime'}
						<h4>Runtimes</h4><p class="control-muted">Inspect installed models and the isolated code sandbox.</p>
						<div class="control-grid"><div class="control-card"><span>Model runtime</span><strong>{workbenchInfo.runtime.generator.available ? workbenchInfo.runtime.generator.alias || 'Local model' : 'No model running'}</strong><p>{workbenchInfo.runtime.generator.message || (workbenchInfo.runtime.generator.is_sleeping?'Sleeping until needed':'Local inference service')}</p><button class="control-button" disabled={!workbenchInfo.runtime.generator.available||workbenchInfo.runtime.busy} onclick={async()=>{try{const response=await fetch('/workbench/model/unload',{method:'POST'});const body=await response.json();if(!response.ok)throw Error(body.message||'Could not release model');message=body.message||body.status;await refresh();}catch(e){message=String(e);}}}>Free AI memory</button></div><div class="control-card"><span>Code sandbox</span><strong>{workbenchInfo.sandbox.ready?'Docker ready':'Docker unavailable'}</strong><p>{workbenchInfo.sandbox.reason||'Isolated local Linux engine'}</p>{#if !workbenchInfo.sandbox.ready}<DockerControl onready={() => void refresh()} />{/if}</div></div>
						<h4 class="runtime-subheading">Installed model assets</h4><div class="control-grid">{#each workbenchInfo.models as model}<div class="control-card"><span>{model.capability.toUpperCase()}</span><strong>{model.model_id}</strong><p>{workbenchInfo.runtime.generator.alias===model.alias&&workbenchInfo.runtime.generator.available?'Loaded':model.assets_present?'Installed':'Files missing'} · {model.enabled?'Enabled':'Disabled'} · {model.quantization} · {model.context.toLocaleString()} context</p><button class="control-button" disabled={!model.assets_present||!model.enabled||workbenchInfo.runtime.busy||runtimeLoading||(workbenchInfo.runtime.generator.alias===model.alias&&!!workbenchInfo.runtime.generator.available)} onclick={async()=>{runtimeLoading=true;message='';try{const response=await fetch('/workbench/model/load',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({capability:model.capability})});const body=await response.json();if(!response.ok)throw Error(body.message||'Model could not load');workbenchInfo=body;message=`Loaded ${model.model_id}.`;}catch(e){message=String(e);}finally{runtimeLoading=false;}}}>{runtimeLoading?'Loading…':'Load model'}</button></div>{/each}</div>
						<div class="control-card"><span>Sandbox policy</span><p>Network {workbenchInfo.sandbox.policy.network} · user {workbenchInfo.sandbox.policy.user} · {workbenchInfo.sandbox.policy.memory_mb} MB memory · {workbenchInfo.sandbox.policy.cpus} CPU · {workbenchInfo.sandbox.policy.timeout_seconds}s limit</p></div>
					{:else if controlSection === 'system'}
						<h4>System & downloads</h4><p class="control-muted">Backend host: {workbenchInfo.host}. Network isolation is {workbenchInfo.network_proof}.</p><button class="control-button" onclick={() => openTab('artifacts')}>View validated downloads</button><div class="control-card"><span>Available tools</span>{#each workbenchInfo.tools as tool}<p>{tool.name}: {tool.available ? 'Available' : 'Unavailable'}</p>{/each}</div>
					{:else}
						<h4>Appearance</h4><p class="control-muted">Choose the display theme. Reduced-motion preferences are honored by the interface.</p><div class="control-actions">{#each ['light','dark','system'] as theme}<button class="control-button" onclick={()=>setMode(theme as 'light'|'dark'|'system')}>{theme}</button>{/each}</div>
					{/if}{/if}
				</div></div>
			</section>
			{/if}
		</div>
		{#if message && !['agent','code','knowledge','workflows'].includes(activeTab)}<div class="border-t border-border px-4 py-2 text-xs text-muted-foreground" role="status" aria-live="polite">{message}{#if message.startsWith('Local workbench disconnected')} <button class="ml-2 underline" onclick={() => void refresh()}>Retry connection</button>{/if}</div>{/if}
	</aside>
{/if}

<style>
  :global(body.sovereign-code-focus #sovereign-documents) { left: 0; z-index: 1000; }
  :global(body.sovereign-code-focus #sovereign-documents > header) { display: none; }
  :global(body.sovereign-code-focus #sovereign-documents .workbench-content.code-view .ide.focus-mode) { height: 100dvh; min-height: 0; }
 .workbench-canvas { position:fixed; left:var(--sidebar-space); right:0; top:0; bottom:0; z-index:20; display:flex; flex-direction:column; background:var(--background); color:var(--foreground); }
 .canvas-hidden,.hidden-view{display:none!important}
 .activity-controls{margin-left:auto;margin-right:16px;display:flex;align-items:center;gap:6px;min-width:0;max-width:46%}
 .activity-chip{display:flex;align-items:center;gap:8px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;border:1px solid var(--border);border-radius:8px;padding:5px 10px;color:var(--muted-foreground);font-size:11px}
 .activity-stop{flex:none;border:1px solid var(--border);border-radius:8px;padding:5px 10px;font-size:11px}
 .activity-chip i{width:7px;height:7px;flex:none;border-radius:50%;background:#7ca6ed;animation:activity-pulse 1.5s infinite}@keyframes activity-pulse{50%{opacity:.35}}
 @media(prefers-reduced-motion:reduce){.activity-chip i{animation:none}}
 .workbench-content { width:100%; max-width:none; margin:0 auto; padding:16px 20px; flex:1; min-height:0; }
 .workbench-content.code-view { padding:0; overflow:hidden; }
 .workbench-content.code-view :global(.ide) { height:calc(100dvh - 51px); border-radius:0; border:0; box-shadow:none; }
 .workbench-canvas header { min-height:50px; height:50px; padding:8px 24px; padding-right:245px; gap:16px; }
 .workbench-header-start{display:flex;align-items:center;gap:10px;min-width:0}.workbench-header-start h2{min-width:0}.workbench-back{display:grid;place-items:center;flex:none;width:30px;height:30px;border:1px solid transparent;border-radius:8px;color:var(--muted-foreground);transition:background .18s,color .18s,border-color .18s}.workbench-back:hover{background:var(--accent);border-color:var(--border);color:var(--foreground)}
 .downloads-page{max-width:1480px;margin:4px auto 28px;color:var(--foreground)}.downloads-heading{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:8px 2px 20px}.downloads-eyebrow{font-size:10px;font-weight:700;letter-spacing:.13em;color:var(--muted-foreground)}.downloads-heading h3{display:flex;align-items:center;gap:10px;margin:4px 0;font-size:25px;font-weight:680;letter-spacing:-.035em}.downloads-heading p{font-size:12px;color:var(--muted-foreground)}.downloads-count{display:inline-grid;place-items:center;min-width:25px;height:23px;padding:0 6px;border:1px solid var(--border);border-radius:7px;font-size:11px;font-weight:600;letter-spacing:0;color:var(--muted-foreground)}.downloads-toolbar{display:flex;align-items:center;gap:8px}.downloads-toolbar button{display:inline-flex;align-items:center;justify-content:center;gap:7px;min-height:34px;padding:7px 12px;border:1px solid var(--border);border-radius:8px;font-size:11px;white-space:nowrap;transition:background .16s,border-color .16s,transform .16s}.downloads-toolbar button:hover{background:var(--accent);border-color:color-mix(in srgb,var(--border) 65%,var(--foreground) 35%);transform:translateY(-1px)}.downloads-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.download-card{min-width:0;padding:15px 16px 12px;border:1px solid var(--border);border-radius:12px;background:color-mix(in srgb,var(--background) 96%,var(--foreground) 4%);box-shadow:0 2px 9px #00000008;transition:border-color .18s,box-shadow .18s,transform .18s}.download-card:hover{border-color:color-mix(in srgb,var(--border) 60%,var(--foreground) 40%);box-shadow:0 8px 22px #00000019;transform:translateY(-1px)}.download-card-main{display:flex;align-items:center;gap:12px;min-width:0}.download-file-icon{display:grid;place-items:center;flex:none;width:38px;height:38px;border-radius:10px;background:color-mix(in srgb,#9a92d7 17%,var(--background));color:#aca7e8}.download-file-icon.word{background:color-mix(in srgb,#4b80dd 17%,var(--background));color:#80a9ee}.download-file-icon.excel{background:color-mix(in srgb,#38a876 17%,var(--background));color:#69c79c}.download-file-icon.slides{background:color-mix(in srgb,#d88955 17%,var(--background));color:#e7a672}.download-file-info{min-width:0;display:flex;flex-direction:column;gap:4px}.download-file-info strong{font-size:13px;font-weight:620;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.download-file-info>span{font-size:11px;color:var(--muted-foreground);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.download-card-bottom{display:flex;align-items:center;gap:10px;margin-top:12px;padding-top:10px;border-top:1px solid var(--border);font-size:10px}.download-task{color:var(--muted-foreground);font-variant-numeric:tabular-nums;white-space:nowrap}.download-validation{display:inline-flex;align-items:center;gap:4px;margin-left:auto;color:#51bf92;white-space:nowrap}.download-validation.failed{color:#e78e87}.download-action{display:inline-flex;align-items:center;justify-content:center;gap:7px;min-height:29px;padding:6px 10px;border-radius:7px;background:var(--foreground);color:var(--background);font-size:11px;font-weight:620;white-space:nowrap;transition:transform .16s,box-shadow .16s,opacity .16s}.download-action:hover{transform:translateY(-1px);box-shadow:0 4px 14px #0003;opacity:.9}.download-delete{display:inline-flex;align-items:center;gap:5px;padding:6px 8px;border:1px solid var(--border);border-radius:7px;color:#e69898;font-size:11px}.download-confirm-backdrop{position:fixed;inset:0;z-index:100;display:grid;place-items:center;background:#000a}.download-confirm{width:min(420px,calc(100% - 32px));padding:22px;border:1px solid var(--border);border-radius:12px;background:var(--background);box-shadow:0 20px 70px #0009}.download-confirm h3{font-size:18px}.download-confirm p{margin:12px 0;color:var(--muted-foreground);overflow-wrap:anywhere}.download-confirm>div{display:flex;justify-content:flex-end;gap:8px}.download-confirm button{padding:8px 12px;border:1px solid var(--border);border-radius:7px}.download-confirm .danger{background:#8e3030;color:white;border-color:#8e3030}.downloads-empty{display:flex;align-items:center;justify-content:center;flex-direction:column;min-height:220px;gap:9px;text-align:center;color:var(--muted-foreground)}.downloads-empty h4{color:var(--foreground);font-size:16px;font-weight:600}.downloads-empty p{max-width:300px;line-height:1.5;font-size:12px}@media(max-width:1080px){.downloads-grid{grid-template-columns:1fr}}@media(max-width:767px){.downloads-page{margin:14px}.downloads-heading{align-items:flex-start;flex-direction:column;gap:13px}.downloads-toolbar{width:100%}.downloads-toolbar button{flex:1}.download-card{padding:13px}.download-card-bottom{gap:7px}}@media(prefers-reduced-motion:reduce){.download-card,.download-action,.downloads-toolbar button{transition:none}.download-card:hover,.download-action:hover,.downloads-toolbar button:hover{transform:none}}
 .control-center{max-width:1120px;margin:25px auto;color:var(--foreground)}.control-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 0 25px;border-bottom:1px solid var(--border)}.control-heading h3{font-size:27px;font-weight:650;letter-spacing:-.035em;margin:5px 0}.control-heading p,.control-muted{color:var(--muted-foreground);line-height:1.55}.control-eyebrow{font-size:10px;letter-spacing:.13em;font-weight:650}.control-layout{display:grid;grid-template-columns:205px minmax(0,1fr);min-height:420px}.control-layout nav{display:flex;flex-direction:column;gap:3px;padding:20px 12px 20px 0;border-right:1px solid var(--border)}.control-layout nav button{padding:10px 12px;border-radius:8px;text-align:left;color:var(--muted-foreground)}.control-layout nav button:hover,.control-layout nav button.selected{background:var(--accent);color:var(--foreground)}.control-body{min-width:0;padding:24px 0 30px 28px}.control-body h4{font-size:19px;font-weight:620;margin-bottom:5px}.control-body .control-muted{margin-bottom:20px}.control-card{padding:16px;border:1px solid var(--border);border-radius:11px;margin:12px 0;background:color-mix(in srgb,var(--background) 96%,var(--foreground) 4%)}.control-card>span{display:block;color:var(--muted-foreground);font-size:10px;text-transform:uppercase;letter-spacing:.1em}.control-card strong{display:block;font-size:14px;margin:6px 0;overflow-wrap:anywhere}.control-card p{font-size:12px;line-height:1.5;color:var(--muted-foreground);margin-top:5px}.control-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.control-button{border:1px solid var(--border);border-radius:8px;padding:9px 12px;font-size:12px;white-space:nowrap}.control-button:hover{background:var(--accent)}.control-actions{display:flex;flex-wrap:wrap;gap:8px}.control-center :focus-visible{outline:2px solid var(--ring);outline-offset:2px}

 @media(max-width:767px) { .workbench-canvas {left:0;top:0;z-index:50;background:var(--background);} .workbench-content {padding:0 0 40px;} .workbench-canvas header{padding:12px 10px;padding-right:230px;font-size:12px}.control-center{margin:16px}.control-heading h3{font-size:22px}.control-layout{display:block}.control-layout nav{flex-direction:row;overflow:auto;border-right:0;border-bottom:1px solid var(--border);padding:12px 0}.control-layout nav button{white-space:nowrap}.control-body{padding:18px 0}.control-grid{grid-template-columns:1fr} }

	#sovereign-documents :is(button, a):focus-visible {
		outline: 2px solid currentColor;
		outline-offset: 2px;
	}
	:global(#sovereign-documents :is(input:not([type='checkbox']):not([type='radio']), textarea):focus-visible) {
		outline: none;
		box-shadow: none;
	}
 @media(max-width:767px){.workbench-canvas header{height:50px;padding:8px 10px;padding-right:225px}.workbench-canvas header h2{max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.workbench-content.code-view{overflow:auto}.workbench-content.code-view :global(.ide){height:auto;min-height:calc(100dvh - 51px)}}
</style>

