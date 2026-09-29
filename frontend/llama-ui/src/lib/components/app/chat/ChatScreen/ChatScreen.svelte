<script lang="ts">
	import ChatScreenActionScrollDown from './ChatScreenActionScrollDown.svelte';
	import ChatScreenDialogsAndAlerts from './ChatScreenDialogsAndAlerts.svelte';
	import ChatScreenGreeting from './ChatScreenGreeting.svelte';
	import { page } from '$app/state';
	import {
		ChatMessages,
		ChatScreenDragOverlay,
		ChatScreenForm,
		ChatScreenServerError,
		ChatScreenStreamResumeStatus,
		ServerLoadingSplash
	} from '$lib/components/app';
	import { LANDING_SETTLE_MAX_MS, LANDING_STABLE_FRAMES, ROUTES } from '$lib/constants';
	import { createAutoScrollController } from '$lib/hooks/use-auto-scroll.svelte';
	import { useChatScreenActiveModel } from '$lib/hooks/use-chat-screen-active-model.svelte';
	import { useChatScreenDragAndDrop } from '$lib/hooks/use-chat-screen-drag-and-drop.svelte';
	import { useChatScreenFileUpload } from '$lib/hooks/use-chat-screen-file-upload.svelte';
	import { useChatScreenScroll } from '$lib/hooks/use-chat-screen-scroll.svelte';
	import { useKeyboardShortcuts } from '$lib/hooks/use-keyboard-shortcuts.svelte';
	import {
		chatStore,
		conversationsStore,
		deviceStore,
		modelsStore,
		serverStore,
		settingsStore
	} from '$lib/stores';
	import { parseFilesToMessageExtras } from '$lib/utils/browser-only';
	import { onDestroy, onMount, tick } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { knowledgeContext } from '$lib/stores/knowledge-context.svelte';

	let { showCenteredEmpty = false } = $props();

	let disableAutoScroll = $derived(
		Boolean(settingsStore.config.disableAutoScroll) || deviceStore.isMobile
	);
	let isMobileUserScrolledUp = $state(false);
	let mobileScrollDownHint = $state(false);
	let mobileScrollDownHintLockedUntil = $state(0);
	let emptyFileNames = $state<string[]>([]);
	let initialMessage = $state('');
	let showDeleteDialog = $state(false);
	let showEmptyFileDialog = $state(false);
	let isEmpty = $derived(
		showCenteredEmpty && conversationsStore.activeMessages.length === 0 && !chatStore.isLoading
	);
	let activeErrorDialog = $derived(chatStore.errorDialogState);
	let isServerLoading = $derived(serverStore.loading);
	let hasPropsError = $derived(!!serverStore.error);
	let isCurrentConversationLoading = $derived(chatStore.isLoading || chatStore.isStreaming());
	let chatFormBottomPosition = $derived.by(() => {
		if (!deviceStore.isMobile) return '1rem';

		if (deviceStore.isStandalone) return '1.5rem';

		if (deviceStore.isIOSSafari) return '0.25rem';

		return '0.5rem';
	});

	const autoScroll = createAutoScrollController();
	const scroll = useChatScreenScroll(autoScroll);
	const activeModel = useChatScreenActiveModel();
	const fileUpload = useChatScreenFileUpload({
		activeModelId: () => activeModel.activeModelId,
		capabilities: () => ({
			hasAudio: activeModel.hasAudioModality,
			hasVideo: activeModel.hasVideoModality,
			hasVision: activeModel.hasVisionModality
		})
	});
	const dragAndDrop = useChatScreenDragAndDrop({
		onDrop: fileUpload.handleFileUpload
	});
	const { handleKeydown } = useKeyboardShortcuts({
		deleteActiveConversation: () => {
			if (conversationsStore.activeConversation) {
				showDeleteDialog = true;
			}
		}
	});

	function handleMobileScroll() {
		if (!deviceStore.isMobile) return;

		const container = scroll.chatScrollContainer;

		if (!container) return;

		const distanceFromBottom =
			container.scrollHeight - container.clientHeight - container.scrollTop;

		isMobileUserScrolledUp = distanceFromBottom > 300;
	}

	async function handleDeleteConfirm() {
		const conversation = conversationsStore.activeConversation;

		if (conversation) {
			await conversationsStore.deleteConversation(conversation.id);
		}

		showDeleteDialog = false;
	}

	async function handleSendMessage(message: string, files?: ChatUploadedFile[]): Promise<boolean> {
		let knowledgeDocuments;
		try {
			knowledgeDocuments =
				files?.length && knowledgeContext.scope === 'all'
					? []
					: await knowledgeContext.resolve('chat');
		} catch (e) {
			toast.error('Could not read connected Knowledge: ' + String(e));
			return false;
		}
		if (knowledgeDocuments.length) {
			if (files?.length) {
				toast.error(
					'Send uploaded files separately, or connect the document from Knowledge. Your attachments remain ready.'
				);
				return false;
			}
			handleSendLikeScroll();
			await chatStore.sendMessage(message, undefined, $state.snapshot(knowledgeDocuments));
			knowledgeContext.pending = [];
			return true;
		}
		const images = files?.filter((file) => /^image\/(?:png|jpeg)$/.test(file.type)) ?? [];
		const chatVisionAvailable =
			serverStore.isRouterMode &&
			modelsStore.models.some((model) => modelsStore.props.modelSupportsVision(model.model));
		if (images.length && !chatVisionAvailable && files?.length !== 1) {
			toast.error('Send one image at a time from Chat, or attach the other files in Agent.');
			return false;
		}
		if (images.length === 1 && files?.length === 1 && !chatVisionAvailable) {
			window.dispatchEvent(
				new CustomEvent('sovereign-open-workspace', {
					detail: {
						tab: 'agent',
						draft: message.trim() || 'Describe this image.',
						image: images[0].file,
						autoSend: true
					}
				})
			);
			return true;
		}
		const plainFiles = files ? $state.snapshot(files) : undefined;
		const result = plainFiles
			? await parseFilesToMessageExtras(plainFiles, activeModel.activeModelId ?? undefined)
			: undefined;

		if (result?.emptyFiles && result.emptyFiles.length > 0) {
			emptyFileNames = result.emptyFiles;
			showEmptyFileDialog = true;

			if (files) {
				const emptyFileNamesSet = new Set(result.emptyFiles);

				fileUpload.uploadedFiles = fileUpload.uploadedFiles.filter(
					(file) => !emptyFileNamesSet.has(file.name)
				);
			}

			return false;
		}

		handleSendLikeScroll();

		await chatStore.sendMessage(message, result?.extras);

		return true;
	}

	let lastScrolledConversationId: string | null = null;

	// Lands at the bottom of a conversation the first time its messages
	// render, whether the route comes from another conversation or from a
	// non-conversation route. The page keeps growing after the first pin
	// without DOM mutations (content-visibility size realizations, syntax
	// highlight passes), so the instant pin repeats every frame until the
	// height settles, bailing out on user scroll or conversation change.
	async function handleMessagesReady(messageCount: number) {
		if (messageCount === 0) return;

		const id = conversationsStore.activeConversation?.id ?? null;

		if (!id || id === lastScrolledConversationId) return;

		lastScrolledConversationId = id;
		await tick();
		autoScroll.scrollToBottom();

		const container = scroll.chatScrollContainer;

		if (!container) return;

		const started = performance.now();

		let stableFrames = 0;
		let lastHeight = container.scrollHeight;

		const settle = () => {
			if (autoScroll.userScrolledUp) return;

			if (conversationsStore.activeConversation?.id !== id) return;

			autoScroll.scrollToBottom();
			const height = container.scrollHeight;

			stableFrames = height === lastHeight ? stableFrames + 1 : 0;
			lastHeight = height;

			if (stableFrames >= LANDING_STABLE_FRAMES) return;

			if (performance.now() - started > LANDING_SETTLE_MAX_MS) return;

			requestAnimationFrame(settle);
		};

		requestAnimationFrame(settle);
	}

	function handleSendLikeScroll() {
		if (!deviceStore.isMobile) {
			autoScroll.enable();
		}

		setTimeout(() => {
			const container = scroll.chatScrollContainer;

			if (!container) return;

			const lastUserBubble = container.querySelector(
				'.chat-message:nth-last-child(2) .chat-message-user .chat-message-user-bubble'
			) as HTMLElement | null;

			if (deviceStore.isMobile) {
				// Keep the last user message bubble just above the input on mobile
				const bubbleHeight = lastUserBubble?.scrollHeight ?? 0;
				const baseHeight = container.scrollHeight - innerHeight;

				container.scrollTo({
					behavior: 'smooth',
					top: bubbleHeight > 0 ? baseHeight - bubbleHeight : baseHeight
				});
			} else {
				// Follow incoming streamed tokens. Pinning the user bubble near the
				// top made long code replies grow behind the fixed composer.
				autoScroll.scrollToBottom();
			}
		}, 100);

		if (deviceStore.isMobile) {
			autoScroll.setDisabled(disableAutoScroll);
			mobileScrollDownHint = true;
			mobileScrollDownHintLockedUntil = Date.now() + 500;
		}
	}

	function handleErrorDialogOpenChange(open: boolean) {
		if (!open) {
			chatStore.dismissErrorDialog();
		}
	}

	async function handleSystemPromptAdd(draft: { message: string; files: ChatUploadedFile[] }) {
		if (draft.message || draft.files.length > 0) {
			chatStore.savePendingDraft(draft.message, draft.files);
		}

		await chatStore.addSystemPrompt();
	}

	$effect(() => {
		const shouldDisableAutoScroll =
			settingsStore.config.disableAutoScroll ||
			(deviceStore.isMobile && isCurrentConversationLoading);

		autoScroll.setDisabled(shouldDisableAutoScroll);

		if (!shouldDisableAutoScroll) {
			autoScroll.enable();
		}
	});

	onMount(() => {
		const pendingDraft = chatStore.consumePendingDraft();

		if (pendingDraft) {
			initialMessage = pendingDraft.message;
			fileUpload.uploadedFiles = pendingDraft.files;
		}

		autoScroll.startObserving();

		if (!disableAutoScroll) {
			autoScroll.enable();
		}

		if (deviceStore.isMobile && isCurrentConversationLoading) {
			mobileScrollDownHint = true;
			mobileScrollDownHintLockedUntil = Date.now() + 500;
		}

		handleMobileScroll();
	});

	onDestroy(() => autoScroll.destroy());
</script>

{#if dragAndDrop.isDragOver}
	<ChatScreenDragOverlay />
{/if}

<svelte:window
	onkeydown={handleKeydown}
	onscroll={(e) => {
		scroll.handleScroll(e);
		handleMobileScroll();

		if (e.isTrusted && Date.now() > mobileScrollDownHintLockedUntil) {
			mobileScrollDownHint = false;
		}
	}}
/>

{#if isServerLoading}
	<ServerLoadingSplash />
{:else}
	<div
		style:--chat-form-bottom-position={chatFormBottomPosition}
		class="chat-screen flex grow flex-col min-h-[calc(100dvh-1rem)] md:min-h-[calc(100dvh-1rem-var(--chat-tabs-offset,0px))] px-4 md:py-0 pt-12 pb-48 md:pb-[calc(var(--chat-form-height,10rem)+4rem)]"
		ondragenter={dragAndDrop.dragHandlers.dragenter}
		ondragleave={dragAndDrop.dragHandlers.dragleave}
		ondragover={dragAndDrop.dragHandlers.dragover}
		ondrop={dragAndDrop.dragHandlers.drop}
		role="main"
	>
		{#if !isEmpty}
			<ChatMessages
				messages={conversationsStore.activeMessages}
				onMessagesReady={handleMessagesReady}
				onUserAction={() => {
					handleSendLikeScroll();
				}}
			/>
		{/if}

		<div
			style:padding-top={!isEmpty ? 'var(--chat-form-padding-top)' : undefined}
			class:empty-chat-composer={isEmpty}
			class={[
				// animate the centered->bottomed move with transform, not bottom:
				// layout-property transitions need the main thread every frame and
				// stutter while a long conversation loads; transform transitions
				// run on the compositor and stay smooth
				'pointer-events-none md:sticky fixed  mt-auto transition-transform duration-200',
				deviceStore.isStandalone
					? 'bottom-6 right-4 left-4'
					: deviceStore.isIOSSafari
						? 'bottom-1 left-2 right-2'
						: 'bottom-2 right-2 left-2',
				'md:bottom-4',
				isEmpty ? 'md:translate-y-[clamp(-16rem,calc(-50dvh+12rem),-4rem)]' : ''
			]}
		>
			<ChatScreenGreeting {isEmpty} />

			<ChatScreenServerError />

			{#if page.params.id}
				<ChatScreenStreamResumeStatus />
			{/if}

			<div class="pointer-events-none flex flex-col gap-6 items-center w-full">
				{#if (deviceStore.isMobile ? mobileScrollDownHint || isMobileUserScrolledUp : autoScroll.userScrolledUp) && page.url.hash.includes(ROUTES.CHAT) && page.params.id}
					<ChatScreenActionScrollDown
						onclick={() => {
							mobileScrollDownHint = false;
							scroll.chatScrollContainer?.scrollTo({
								behavior: 'smooth',
								top: scroll.chatScrollContainer.scrollHeight
							});
						}}
					/>
				{/if}
			</div>

			<ChatScreenForm
				bind:uploadedFiles={fileUpload.uploadedFiles}
				class="pointer-events-auto conversation-chat-form"
				disabled={hasPropsError || chatStore.isEditing()}
				{initialMessage}
				isLoading={isCurrentConversationLoading}
				onFileRemove={fileUpload.handleFileRemove}
				onFileUpload={fileUpload.handleFileUpload}
				onSend={handleSendMessage}
				onStop={() => chatStore.stopGeneration()}
				onSystemPromptAdd={handleSystemPromptAdd}
			/>
		</div>
	</div>
{/if}

<ChatScreenDialogsAndAlerts
	{activeErrorDialog}
	{emptyFileNames}
	{fileUpload}
	{handleDeleteConfirm}
	{handleErrorDialogOpenChange}
	{showDeleteDialog}
	{showEmptyFileDialog}
/>

<style>
	@media (min-width: 768px) and (max-height: 760px) {
		.chat-screen .empty-chat-composer {
			transform: translateY(calc(-50dvh + 23rem));
		}
	}
</style>
