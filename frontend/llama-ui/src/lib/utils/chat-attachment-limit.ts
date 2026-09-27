// Keep a single file excerpt comfortably below the 4096-token local model context.
// Exact token counts vary by document; the full file belongs in the Documents panel.
export const CHAT_ATTACHMENT_CHAR_LIMIT = 4000;

export function limitChatAttachment(content: string, availableCharacters = CHAT_ATTACHMENT_CHAR_LIMIT): { text: string; truncated: boolean; used: number } {
	const allowance = Math.max(0, Math.min(availableCharacters, CHAT_ATTACHMENT_CHAR_LIMIT));
	if (content.length <= allowance) return { text: content, truncated: false, used: content.length };
	return {
		text: content.slice(0, allowance) +
			'\n[Attachment excerpt ends here. Import the full file in Documents for a grounded answer.]',
		truncated: true,
		used: allowance
	};
}
