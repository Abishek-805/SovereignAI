import { DatabaseService } from './database.service';
import { MessageRole, MessageType } from '$lib/enums';
import type { KnowledgeSource } from './knowledge.service';

/** Move the former document-assistant history into normal Chat, without deleting originals. */
export async function migrateKnowledgeHistory() {
	const legacy = JSON.parse(localStorage.getItem('sovereign-knowledge-history') || '[]');
	if (!Array.isArray(legacy) || !legacy.length) return;
	const existing = await DatabaseService.getAllConversations();
	for (const session of legacy) {
		if (
			!session.id ||
			!Array.isArray(session.turns) ||
			existing.some((conv) => conv.legacyKnowledgeChatId === session.id)
		)
			continue;
		const conversation = await DatabaseService.createConversation(
			session.title || 'Document conversation'
		);
		const sources = session.turns.flatMap(
			(turn: { result?: { sources?: KnowledgeSource[] } }) => turn.result?.sources || []
		);
		const references = Array.isArray(session.selected)
			? session.selected
					.filter((id: unknown) => typeof id === 'string')
					.map((id: string) => ({
						id,
						name:
							sources.find((source: KnowledgeSource) => source.document_id === id)?.display_name ||
							id
					}))
			: [];
		let parent = await DatabaseService.createRootMessage(conversation.id);
		for (const turn of session.turns) {
			if (typeof turn.question !== 'string') continue;
			const common = {
				convId: conversation.id,
				type: MessageType.TEXT,
				timestamp: session.updatedAt || Date.now(),
				children: []
			};
			const user = await DatabaseService.createMessageBranch(
				{
					...common,
					parent,
					role: MessageRole.USER,
					content: turn.question,
					...(references.length ? { knowledgeDocuments: references } : {})
				},
				parent
			);
			const assistant = await DatabaseService.createMessageBranch(
				{
					...common,
					parent: user.id,
					role: MessageRole.ASSISTANT,
					content: turn.result?.answer || 'Request did not finish.',
					knowledgeSources: (turn.result?.sources || []) as KnowledgeSource[],
					knowledgeDownloads: turn.result?.downloads || {},
					knowledgeStatus: turn.result?.status
				},
				user.id
			);
			parent = assistant.id;
		}
		await DatabaseService.updateConversation(conversation.id, {
			legacyKnowledgeChatId: session.id,
			lastModified: session.updatedAt || Date.now(),
			...(references.length ? { knowledgeDocuments: references } : {})
		});
	}
}
