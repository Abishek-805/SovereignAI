<script lang="ts">
	import Plus from '@lucide/svelte/icons/plus';
	import FileText from '@lucide/svelte/icons/file-text';
	import Paperclip from '@lucide/svelte/icons/paperclip';
	import Image from '@lucide/svelte/icons/image';
	import { knowledgeContext } from '$lib/stores/knowledge-context.svelte';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import { getChatFormActionsContext } from '$lib/contexts';
	const context = getChatFormActionsContext();
</script>

<DropdownMenu.Root
	><DropdownMenu.Trigger
		class="flex h-9 items-center gap-2 rounded-lg px-2 hover:bg-accent"
		aria-label="Add context"
		><Plus size={16} /><span class="text-xs">Add context</span></DropdownMenu.Trigger
	><DropdownMenu.Content align="start" class="w-52"
		><DropdownMenu.Item onclick={() => (knowledgeContext.pickerOpen = true)}
			><FileText size={16} />From Knowledge</DropdownMenu.Item
		><DropdownMenu.Item onclick={() => context.onFileUpload?.()}
			><Paperclip size={16} />Upload file</DropdownMenu.Item
		><DropdownMenu.Item
			onclick={() => window.dispatchEvent(new Event('sovereign-choose-chat-image'))}
			><Image size={16} />Add image</DropdownMenu.Item
		></DropdownMenu.Content
	></DropdownMenu.Root
>
