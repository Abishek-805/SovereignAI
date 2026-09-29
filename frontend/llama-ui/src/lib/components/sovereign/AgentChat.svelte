<script lang="ts">
	import {
		decodeAgentResponse,
		agentGoalError,
		agentConversationHistory,
		agentProblem
	} from '$lib/services/agent-request.service';
	import './agent-workspace.css';
	import type { RoutingTelemetry } from '$lib/services/routing-telemetry';
	import RouteDetails from './RouteDetails.svelte';
	import MarkdownContent from '$lib/components/app/content/MarkdownContent/MarkdownContent.svelte';
	import { onMount, tick, untrack } from 'svelte';
	import Paperclip from '@lucide/svelte/icons/paperclip';
	import ArrowUp from '@lucide/svelte/icons/arrow-up';
	import Sparkles from '@lucide/svelte/icons/sparkles';
	import X from '@lucide/svelte/icons/x';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import FolderCode from '@lucide/svelte/icons/folder-code';
	import History from '@lucide/svelte/icons/history';
	import Plus from '@lucide/svelte/icons/plus';
	import { CodingWorkspaceService } from '$lib/services/coding-workspace.service';
	import KnowledgePicker from './KnowledgePicker.svelte';
	import KnowledgeConnection from './KnowledgeConnection.svelte';
	import KnowledgeChips from './KnowledgeChips.svelte';
	import KnowledgeSources from './KnowledgeSources.svelte';
	import DuplicateAudit from './DuplicateAudit.svelte';
	import { removedDuplicateGroups, type DuplicateGroup } from '$lib/services/duplicate-audit';
	import { knowledgeContext } from '$lib/stores/knowledge-context.svelte';
	import type { KnowledgeSource } from '$lib/services/knowledge.service';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import FileText from '@lucide/svelte/icons/file-text';
	import Image from '@lucide/svelte/icons/image';
	let pickerOpen = $state(false);
	let threadElement = $state<HTMLDivElement>();
	let followLatest = true;
	let visibleTurnCount = 0;
	$effect(() => {
		const count = turns.length;
		const latest = turns.at(-1);
		void latest?.answer;
		void latest?.status;
		void agentStages.length;
		const element = threadElement;
		const shouldFollow = followLatest || count !== visibleTurnCount;
		visibleTurnCount = count;
		// Keep new turns in view while leaving an older message readable when the user scrolls up.
		void tick().then(() => {
			if (element && shouldFollow) element.scrollTop = element.scrollHeight;
		});
	});
	let attachmentInput: HTMLInputElement;
	function chooseFiles(images = false) {
		attachmentInput.accept = images
			? '.png,.jpg,.jpeg'
			: '.pdf,.docx,.txt,.md,.csv,.json,.log,.xlsx,.pptx';
		attachmentInput.click();
	}
	let {
		draft = '',
		incomingImage = null,
		autoSend = false,
		requestId = ''
	}: {
		draft?: string;
		incomingImage?: File | null;
		autoSend?: boolean;
		requestId?: string;
	} = $props();
	type Turn = {
		duplicateGroups?: DuplicateGroup[];
		routing?: RoutingTelemetry;
		question: string;
		answer: string;
		status: string;
		attachments?: string[];
		coverage?: import('$lib/services/knowledge.service').KnowledgeCoverage;
		sources?: KnowledgeSource[];
		details?: string;
		downloads?: Record<string, string>;
		workspace?: string;
		taskId?: string;
		diff?: string;
		added?: number;
		removed?: number;
		review?: boolean;
	};
	let lastDraft = '';
	$effect(() => {
		const next = draft;
		if (next && next !== lastDraft) {
			lastDraft = next;
			prompt = next;
		}
	});
	let prompt = $state(''),
		turns = $state<Turn[]>([]),
		busy = $state(false),
		notice = $state('');
	type AgentSession = {
		id: string;
		title: string;
		updatedAt: number;
		turns: Turn[];
		documents?: { id: string; name: string }[];
		knowledgeConnected?: boolean;
		knowledgeScope?: 'all' | 'selected';
	};
	let sessions = $state<AgentSession[]>([]),
		chatId = $state(''),
		historyOpen = $state(false);
	let attached = $state<{ id: string; name: string }[]>([]),
		image = $state<File | null>(null),
		workspace = $state('');
	let lastIncomingImage: File | null = null;
	$effect(() => {
		const next = incomingImage;
		if (!next || next === lastIncomingImage || busy) return;
		lastIncomingImage = next;
		image = next;
		prompt = draft || 'Describe this image.';
		if (autoSend) queueMicrotask(() => void send());
	});
	let lastTextRequestId = '';
	$effect(() => {
		const id = requestId;
		if (
			!id ||
			id === lastTextRequestId ||
			!autoSend ||
			incomingImage ||
			busy ||
			!projectsReady ||
			!draft.trim()
		)
			return;
		lastTextRequestId = id;
		prompt = draft;
		queueMicrotask(() => void send());
	});
	let agentJob = $state(''),
		agentStages = $state<string[]>([]),
		agentElapsed = $state(0),
		stopRequested = $state(false);
	let agentAbort: AbortController | null = null;
	let projects = $state<{ workspace_id: string; name: string }[]>([]);
	let projectsReady = $state(false);
	let projectMenu = $state(false);
	let projectControl: HTMLDivElement;
	function dismissProjectMenu(event: MouseEvent) {
		if (projectMenu && projectControl && !projectControl.contains(event.target as Node))
			projectMenu = false;
	}
	function projectMenuKeydown(event: KeyboardEvent) {
		if (projectMenu && event.key === 'Escape') {
			event.preventDefault();
			projectMenu = false;
		}
	}
	function activity(running: boolean, stage: string) {
		window.dispatchEvent(
			new CustomEvent('sovereign-activity', {
				detail: { view: 'Agent', running, stage, jobId: agentJob }
			})
		);
	}
	async function stopAgent() {
		stopRequested = true;
		notice = 'Stopping after the current step…';
		if (agentJob) await fetch('/coding/jobs/' + agentJob + '/stop', { method: 'POST' });
		else agentAbort?.abort();
	}
	function persist() {
		sessionStorage.setItem('sovereign-agent-turns', JSON.stringify(turns.slice(-20)));
		sessionStorage.setItem('sovereign-agent-chat-id', chatId);
		if (turns.length && chatId) {
			sessions = [
				{
					id: chatId,
					title: turns[0].question.slice(0, 60),
					updatedAt: Date.now(),
					turns: turns.slice(-30),
					documents: $state.snapshot(knowledgeContext.agent),
					knowledgeConnected: knowledgeContext.agentConnected,
					knowledgeScope: knowledgeContext.agentScope
				},
				...sessions.filter((item) => item.id !== chatId)
			].slice(0, 30);
			localStorage.setItem('sovereign-agent-history', JSON.stringify(sessions));
		}
	}
	function newAgentChat() {
		if (busy) return;
		chatId = crypto.randomUUID();
		turns = [];
		prompt = '';
		image = null;
		attached = [];
		knowledgeContext.agent = [];
		knowledgeContext.agentConnected = true;
		knowledgeContext.agentScope = 'all';
		notice = '';
		historyOpen = false;
		sessionStorage.removeItem('sovereign-agent-turns');
		sessionStorage.setItem('sovereign-agent-chat-id', chatId);
	}
	function openAgentChat(session: AgentSession) {
		if (busy) return;
		chatId = session.id;
		turns = session.turns;
		knowledgeContext.agent = session.documents || [];
		knowledgeContext.agentConnected = session.knowledgeConnected ?? true;
		knowledgeContext.agentScope = session.knowledgeScope ?? 'all';
		prompt = '';
		historyOpen = false;
		persist();
	}
	function deleteAgentChat(id: string) {
		if (busy) return;
		sessions = sessions.filter((item) => item.id !== id);
		localStorage.setItem('sovereign-agent-history', JSON.stringify(sessions));
		if (chatId === id) newAgentChat();
	}
	function openCodeReview(turn: Turn) {
		if (!turn.workspace || !turn.taskId) return;
		localStorage.setItem('sovereign-active-workspace', turn.workspace);
		window.dispatchEvent(
			new CustomEvent('sovereign-open-workspace', { detail: { tab: 'code', taskId: turn.taskId } })
		);
	}
	async function json(response: Response) {
		return decodeAgentResponse(response);
	}
	let contextReady = $state(false);
	$effect(() => {
		if (contextReady) {
			sessionStorage.setItem('sovereign-agent-context', JSON.stringify(knowledgeContext.agent));
			sessionStorage.setItem(
				'sovereign-agent-knowledge-options',
				JSON.stringify({
					connected: knowledgeContext.agentConnected,
					scope: knowledgeContext.agentScope
				})
			);
		}
	});
	$effect(() => {
		void knowledgeContext.agentConnected;
		void knowledgeContext.agentScope;
		void knowledgeContext.agent;
		if (contextReady) untrack(persist);
	});
	onMount(() => {
		if (!knowledgeContext.agent.length) {
			try {
				knowledgeContext.agent = JSON.parse(
					sessionStorage.getItem('sovereign-agent-context') || '[]'
				);
			} catch {}
		}
		try {
			const options = JSON.parse(
				sessionStorage.getItem('sovereign-agent-knowledge-options') || '{}'
			);
			knowledgeContext.agentConnected = options.connected ?? true;
			knowledgeContext.agentScope = options.scope ?? 'all';
		} catch {}
		contextReady = true;
		if (!autoSend) prompt = draft;
		try {
			sessions = JSON.parse(localStorage.getItem('sovereign-agent-history') || '[]');
			chatId = sessionStorage.getItem('sovereign-agent-chat-id') || crypto.randomUUID();
			turns = JSON.parse(sessionStorage.getItem('sovereign-agent-turns') || '[]');
			if (!sessionStorage.getItem('sovereign-agent-chat-id') && !turns.length && sessions.length) {
				chatId = sessions[0].id;
				turns = sessions[0].turns;
			}
		} catch {
			chatId = crypto.randomUUID();
		}
		void CodingWorkspaceService.list()
			.then((items) => {
				projects = items;
				const id = localStorage.getItem('sovereign-active-workspace');
				if (items.some((item) => item.workspace_id === id)) workspace = id || '';
			})
			.catch((e) => (notice = String(e)))
			.finally(() => (projectsReady = true));
		const pending = sessionStorage.getItem('sovereign-agent-job');
		if (pending) {
			const index = turns.findIndex((turn) => turn.status === 'working');
			if (index >= 0) {
				busy = true;
				agentJob = pending;
				void poll(index, pending);
			} else sessionStorage.removeItem('sovereign-agent-job');
		}
	});
	async function attach(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		await attachFiles(Array.from(input.files || []));
		input.value = '';
	}
	let dragOver = $state(false);
	async function attachFiles(files: File[]) {
		if (busy) {
			notice = 'Wait for the current task before adding files.';
			return;
		}
		if (files.filter((file) => /\.(png|jpe?g)$/i.test(file.name)).length > 1) {
			notice = 'Add one image at a time. No attachments were changed.';
			return;
		}
		busy = true;
		try {
			for (const file of files) {
				if (/\.(png|jpe?g)$/i.test(file.name)) {
					if (file.size > 5 * 1024 * 1024) throw new Error('Use an image up to 5 MB.');
					image = file;
					continue;
				}
				notice = 'Reading ' + file.name + '…';
				const form = new FormData();
				form.append('file', file, file.name.split(/[\\/]/).at(-1) || file.name);
				const doc = await json(await fetch('/documents/import', { method: 'POST', body: form }));
				attached = [...attached, { id: doc.document_id, name: file.name }];
			}
			notice = 'Files ready.';
		} catch (e) {
			notice = String(e);
		} finally {
			busy = false;
		}
	}
	function finish(index: number, result: any) {
		const original = turns[index];
		const operations = Array.isArray(result.result?.operations) ? result.result.operations : [];
		const edited = [...operations].reverse().find((operation: any) => operation.tool === 'file_edit' && operation.result?.state === 'completed')?.result;
		const editResult = result.plan?.action === 'edit_code' ? result.result : edited;
		const edit = !!editResult;
		const diff = editResult?.diff || '';
		if (operations.some((operation: any) => typeof operation.tool === 'string' && operation.tool.startsWith('document_'))) void knowledgeContext.refresh().catch((error) => { notice = 'Task finished, but the Knowledge list could not refresh: ' + String(error); });
		const lines = diff.split('\n');
		turns[index] = {
			duplicateGroups: removedDuplicateGroups(operations),
			question: original.question,
			attachments: original.attachments,
			routing: result.routing || result.result?.routing || original.routing,
			answer: result.result?.state === 'failed' ? agentProblem(result.answer) : result.answer || 'Task finished. See details.',
			status: result.result?.state === 'failed' ? 'failed' : result.status || 'completed',
			sources: result.result?.sources || result.sources || [],
			coverage: result.result?.coverage || result.coverage,
			downloads: result.downloads || result.result?.downloads,
			workspace: edit ? result.workspace_id : undefined,
			taskId: edit ? editResult?.task_id : undefined,
			diff,
			added: lines.filter((line: string) => line.startsWith('+') && !line.startsWith('+++')).length,
			removed: lines.filter((line: string) => line.startsWith('-') && !line.startsWith('---'))
				.length,
			details: JSON.stringify(
				{
					plan: result.plan,
					steps: result.steps,
					checks: result.result?.checks,
					sources: result.result?.sources
				},
				null,
				2
			)
		};
		if (result.routing)
			window.dispatchEvent(
				new CustomEvent('sovereign-route', {
					detail: { task: result.plan?.action || 'Agent', ...result.routing }
				})
			);
		if (result.workspace_id) {
			workspace = result.workspace_id;
			localStorage.setItem('sovereign-active-workspace', workspace);
			void CodingWorkspaceService.list().then((items) => (projects = items));
		}
		persist();
	}
	async function undoTurn(index: number) {
		const turn = turns[index];
		if (!turn.workspace || !turn.taskId) return;
		try {
			await CodingWorkspaceService.undo(turn.workspace, turn.taskId);
			turns[index] = {
				...turn,
				status: 'undone',
				answer: `Reverted ${turn.workspace ? 'the applied file change' : 'the change'}.`,
				review: false
			};
			persist();
		} catch (e) {
			notice = String(e);
		}
	}
	async function poll(index: number, id: string) {
		try {
			let result = await json(await fetch('/coding/jobs/' + id));
			while (result.state === 'running') {
				notice = result.stage;
				agentElapsed = result.elapsed;
				agentStages = (result.events || []).map((event: { stage: string }) => event.stage);
				activity(true, result.stage);
				await new Promise((resolve) => setTimeout(resolve, 650));
				result = await json(await fetch('/coding/jobs/' + id));
			}
			if (result.routing) { turns[index] = {...turns[index], routing: result.routing}; persist(); }
			if (result.error) throw Error(result.error);
			if (result.state === 'cancelled') throw Error('Task stopped');
			finish(index, result.result);
			notice = '';
		} catch (e) {
			turns[index] = {
				...turns[index],
				question: turns[index].question,
				answer: stopRequested ? 'Task stopped.' : agentProblem(e),
				status: stopRequested ? 'stopped' : 'failed'
			};
			notice = stopRequested
				? 'Task stopped.'
				: 'The task could not finish. Review the details and retry.';
		} finally {
			busy = false;
			agentJob = '';
			sessionStorage.removeItem('sovereign-agent-job');
			persist();
			activity(false, '');
		}
	}
	async function send() {
		if (!prompt.trim() || busy) return;
		if (
			image &&
			(attached.length ||
				(knowledgeContext.agentConnected &&
					knowledgeContext.agentScope === 'selected' &&
					knowledgeContext.agent.length))
		) {
			notice = 'Send the image and documents separately. Both attachments remain ready.';
			return;
		}
		const goalError = agentGoalError(prompt.trim());
		if (goalError) {
			notice = goalError;
			return;
		}
		stopRequested = false;
		agentJob = '';
		busy = true;
		agentStages = [];
		agentElapsed = 0;
		notice = 'Preparing request…';
		let connectedDocuments;
		try {
			connectedDocuments = image ? [] : await knowledgeContext.resolve('agent');
		} catch (e) {
			notice = 'Could not read connected Knowledge: ' + String(e);
			busy = false;
			activity(false, '');
			return;
		}
		const question = prompt.trim();
		const sentImage = image;
		const sentDocuments = [
			...new Map(
				[...connectedDocuments, ...attached.map((doc) => ({ id: doc.id, name: doc.name }))].map(
					(doc) => [doc.id, doc]
				)
			).values()
		];
		const history = agentConversationHistory(
			turns.map((t) => ({ instruction: t.question, answer: t.answer, state: t.status }))
		);
		prompt = '';
		image = null;
		attached = [];
		turns = [
			...turns,
			{
				question,
				answer: '',
				status: 'working',
				attachments: [
					...sentDocuments.map((doc) => doc.name),
					...(sentImage ? [sentImage.name] : [])
				]
			}
		];
		const index = turns.length - 1;
		busy = true;
		notice = 'Preparing local task…';
		persist();
		activity(true, notice);
		try {
			if (sentImage) {
				const form = new FormData();
				form.append('file', sentImage);
				form.append('question', question);
				// Do not abort submission before its job ID arrives: a queued Stop
				// must cancel the owned backend job, not only the upload socket.
				const result = await json(
					await fetch('/agent/vision/jobs', { method: 'POST', body: form })
				);
				agentJob = result.job_id;
				sessionStorage.setItem('sovereign-agent-job', agentJob);
				activity(true, notice);
				if (stopRequested) await fetch('/coding/jobs/' + agentJob + '/stop', { method: 'POST' });
				agentStages = [];
				await poll(index, agentJob);
				return;
			}
			const result = await json(
				await fetch('/agent/jobs', {
					method: 'POST',
					headers: { 'content-type': 'application/json' },
					body: JSON.stringify({
						goal: question,
						document_ids: sentDocuments.map((d) => d.id),
						workspace_id: workspace || null,
						history
					})
				})
			);
			agentJob = result.job_id;
			sessionStorage.setItem('sovereign-agent-job', agentJob);
			activity(true, notice);
			if (stopRequested) await fetch('/coding/jobs/' + agentJob + '/stop', { method: 'POST' });
			agentStages = [];
			await poll(index, agentJob);
		} catch (e) {
			agentAbort = null;
			turns[index] = {
				...turns[index],
				question,
				answer: stopRequested ? 'Task stopped.' : agentProblem(e),
				status: stopRequested ? 'stopped' : 'failed'
			};
			busy = false;
			notice = stopRequested ? 'Task stopped.' : 'The task could not start.';
			persist();
			activity(false, '');
		}
	}
</script>

<svelte:window onclick={dismissProjectMenu} onkeydown={projectMenuKeydown} />
<KnowledgePicker
	bind:open={pickerOpen}
	selected={knowledgeContext.agentScope === 'all'
		? knowledgeContext.catalog
		: knowledgeContext.agent}
	scope={knowledgeContext.agentScope}
	onconnect={(docs, scope) => knowledgeContext.setAgent(docs, scope)}
/>
<section class="agent-chat" class:empty={!turns.length} aria-label="Local agent">
	<header class="agent-topbar">
		<div>
			<Sparkles size={17} /><strong>Agent</strong><span
				>{projects.find((project) => project.workspace_id === workspace)?.name ||
					'No project selected'}</span
			>
		</div>
		<div class="agent-top-actions">
			<button
				class="history-trigger"
				aria-expanded={historyOpen}
				onclick={() => (historyOpen = !historyOpen)}
				><History size={14} /> History {sessions.length || ''}</button
			><button class="open-code" onclick={newAgentChat} disabled={busy}
				><Plus size={14} /> New chat</button
			>
		</div>
	</header>
	{#if historyOpen}<div class="agent-history" aria-label="Agent conversation history">
			{#if sessions.length}{#each sessions as session}<div
						class="agent-history-row"
						class:current={session.id === chatId}
					>
						<button onclick={() => openAgentChat(session)}
							><strong>{session.title}</strong><small
								>{new Date(session.updatedAt).toLocaleString()} · {session.turns.length} turns</small
							></button
						><button
							aria-label={'Delete ' + session.title}
							onclick={() => deleteAgentChat(session.id)}><X size={14} /></button
						>
					</div>{/each}{:else}<p>No past conversations yet.</p>{/if}
		</div>{/if}
	<div
		class="thread"
		bind:this={threadElement}
		onscroll={() => {
			if (threadElement)
				followLatest =
					threadElement.scrollHeight - threadElement.scrollTop - threadElement.clientHeight < 48;
		}}
	>
		{#if !turns.length}<div class="welcome">
				<h2>What would you like to do?</h2>
				<p>Ask a question or give me a task. Bring your files when you need them.</p>
				<div class="examples">
					{#each ['Summarize a document', 'Inspect my project', 'Create a report'] as example}<button
							onclick={() => (prompt = example)}><span>{example}</span></button
						>{/each}
				</div>
			</div>{/if}{#each turns as turn, index}<article>
				<div class="user-message">
					{turn.question}
				</div>
				<div class="assistant-message" class:failed={turn.status === 'failed'}>
					{#if turn.status === 'working'}<div class="working" role="status">
							<div class="working-head">
								<span class="working-dot"></span><strong>{notice || 'Working locally'}</strong><span
									>{agentElapsed}s</span
								>
							</div>
							<div class="steps">
								{#each agentStages.slice(-6) as step, i}<div
										class:current={i === agentStages.slice(-6).length - 1}
									>
										<span>{i === agentStages.slice(-6).length - 1 ? '◉' : '·'}</span>{step}
									</div>{/each}
							</div>
							{#if agentJob}<button class="stop-task" onclick={stopAgent}>Stop task</button>{/if}
						</div>{:else}<div class="agent-answer">
							<MarkdownContent content={turn.answer || ''} />
						</div>
						<DuplicateAudit groups={turn.duplicateGroups} />
						<RouteDetails routing={turn.routing} compact />
						<KnowledgeSources
							sources={turn.sources || []}
							coverage={turn.coverage}
						/>{#if turn.downloads}<div class="downloads">
								{#each Object.entries(turn.downloads) as [kind, url]}<a href={url}
										>Download {kind}</a
									>{/each}
							</div>{/if}{#if turn.workspace}<div class="agent-change-card">
								<strong
									>{turn.status === 'completed'
										? 'File edited'
										: turn.status === 'undone'
											? 'Change undone'
											: 'Edit not applied'}</strong
								><span
									>{turn.diff ? `+${turn.added || 0} −${turn.removed || 0}` : 'No saved diff'}</span
								>
								<div class="change-buttons">
									<button onclick={() => openCodeReview(turn)} disabled={!turn.taskId}
										>Review changes</button
									>{#if turn.status === 'completed' && turn.taskId}<button
											onclick={() => void undoTurn(index)}>Undo</button
										>{/if}<button onclick={() => openCodeReview(turn)}>Open code workspace →</button
									>
								</div>
								{#if turn.review}<pre class="agent-diff">{turn.diff ||
											'No file changes were applied.'}</pre>{/if}
							</div>{/if}{/if}
				</div>
			</article>{/each}
	</div>
	<div class="composer-wrap">
		<form
			class="composer"
			class:agent-drop-active={dragOver}
			ondragover={(event) => {
				if (event.dataTransfer?.types.includes('Files')) {
					event.preventDefault();
					dragOver = true;
				}
			}}
			ondragleave={(event) => {
				if (!event.currentTarget.contains(event.relatedTarget as Node)) dragOver = false;
			}}
			ondrop={(event) => {
				event.preventDefault();
				dragOver = false;
				if (event.dataTransfer) void attachFiles(Array.from(event.dataTransfer.files));
			}}
			onsubmit={(e) => {
				e.preventDefault();
				void send();
			}}
		>
			{#if dragOver}<p class="agent-drop-hint">Drop documents or an image to add context</p>{/if}
			<KnowledgeConnection target="agent" disabled={busy} onchoose={() => (pickerOpen = true)} />
			<KnowledgeChips
				documents={knowledgeContext.agentConnected && knowledgeContext.agentScope === 'selected'
					? knowledgeContext.agent
					: []}
				onremove={(id) =>
					(knowledgeContext.agent = knowledgeContext.agent.filter((doc) => doc.id !== id))}
			/>
			{#if attached.length || image}<div class="attachments">
					{#each attached as doc}<span
							>{doc.name}<button
								type="button"
								aria-label={'Remove ' + doc.name}
								onclick={() => (attached = attached.filter((d) => d.id !== doc.id))}
								><X size={12} /></button
							></span
						>{/each}{#if image}<span
							>{image.name}<button
								type="button"
								aria-label="Remove image"
								onclick={() => (image = null)}><X size={12} /></button
							></span
						>{/if}
				</div>{/if}
			<textarea
				aria-label="Task request"
				bind:value={prompt}
				placeholder="Ask anything or describe a task…"
				onkeydown={(e) => {
					if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
						e.preventDefault();
						void send();
					}
				}}
			></textarea>
			<div class="composer-tools">
				<input
					class="hidden"
					bind:this={attachmentInput}
					type="file"
					multiple
					onchange={attach}
					disabled={busy}
				/><DropdownMenu.Root
					><DropdownMenu.Trigger class="agent-add-context" disabled={busy}
						><Plus size={15} /> Add context</DropdownMenu.Trigger
					><DropdownMenu.Content
						><DropdownMenu.Item onclick={() => (pickerOpen = true)}
							><FileText size={15} /> From Knowledge</DropdownMenu.Item
						><DropdownMenu.Item onclick={() => chooseFiles()}
							><Paperclip size={15} /> Upload files</DropdownMenu.Item
						><DropdownMenu.Item onclick={() => chooseFiles(true)}
							><Image size={15} /> Add images</DropdownMenu.Item
						></DropdownMenu.Content
					></DropdownMenu.Root
				>
				<div class="project-control" bind:this={projectControl}>
					<button
						type="button"
						class="project-trigger"
						aria-label="Project context"
						aria-expanded={projectMenu}
						onclick={() => (projectMenu = !projectMenu)}
						><FolderCode size={15} /><span
							>{projects.find((project) => project.workspace_id === workspace)?.name ||
								'No project'}</span
						><ChevronDown size={13} /></button
					>{#if projectMenu}<div class="project-options" role="group" aria-label="Select project">
							<button
								type="button"
								class:chosen={!workspace}
								onclick={() => {
									workspace = '';
									projectMenu = false;
								}}>No project</button
							>{#each projects as project}<button
									type="button"
									class:chosen={workspace === project.workspace_id}
									onclick={() => {
										workspace = project.workspace_id;
										projectMenu = false;
									}}>{project.name}</button
								>{/each}
						</div>{/if}
				</div>
				<span class="spacer"></span><span class="local-label">Automatic · Local</span
				>{#if busy}<button type="button" class="composer-stop" onclick={stopAgent}>Stop</button
					>{/if}<button class="send" aria-label="Send task" disabled={busy || !prompt.trim()}
					><ArrowUp size={18} /></button
				>
			</div>
		</form>
		<p class="notice" role="status">{notice || 'Enter to send · Shift+Enter for a new line'}</p>
	</div>
</section>
