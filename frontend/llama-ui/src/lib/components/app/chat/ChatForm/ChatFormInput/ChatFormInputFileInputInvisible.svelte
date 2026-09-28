<script lang="ts">
	interface Props {
		class?: string;
		multiple?: boolean;
		onFileSelect?: (files: File[]) => void;
	}

	let { class: className = '', multiple = true, onFileSelect }: Props = $props();

	let fileInputElement: HTMLInputElement | undefined;

	export function click(accept = '') {
		if (fileInputElement) fileInputElement.accept = accept;
		fileInputElement?.click();
	}

	function handleFileSelect(event: Event) {
		const input = event.target as HTMLInputElement;

		if (input.files) {
			onFileSelect?.(Array.from(input.files));
		}
		input.value = '';
	}
</script>

<input
	bind:this={fileInputElement}
	class="hidden {className}"
	{multiple}
	onchange={handleFileSelect}
	type="file"
/>
