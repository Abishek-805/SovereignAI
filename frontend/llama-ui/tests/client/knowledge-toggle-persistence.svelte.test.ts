import { afterEach, describe, expect, it } from 'vitest';
import { DatabaseService } from '$lib/services/database.service';
import { MessageRole, MessageType } from '$lib/enums';

const ownedIds: string[] = [];
afterEach(async () => {
	await DatabaseService.bulkDeleteConversations(ownedIds.splice(0));
});

describe('reactive records at the IndexedDB boundary', () => {
	it('persists Knowledge Off and On after a model answer with nested route history', async () => {
		const conversation = await DatabaseService.createConversation('Knowledge toggle regression');
		ownedIds.push(conversation.id);
		const answer = await DatabaseService.createMessageBranch({
			convId: conversation.id, parent: null, children: [], timestamp: Date.now(),
			role: MessageRole.ASSISTANT, type: MessageType.TEXT, content: 'I am SovereignAI.'
		}, null);
		let history = $state({
			knowledgeDocuments: [{ id: 'fixture-document', name: 'Fixture.txt' }],
			routing: { decision: { intent: 'answer', request_id: 'fixture-request', candidate_models: ['fixture-model'], inference_time: 0.1 } }
		});
		// These are real Svelte browser proxies; IndexedDB rejects them without a snapshot.
		expect(() => structuredClone(history)).toThrow();
		await DatabaseService.updateMessage(answer.id, { routing: history.routing });
		await DatabaseService.updateConversation(conversation.id, {
			knowledgeConnected: false, knowledgeScope: 'selected', knowledgeDocuments: history.knowledgeDocuments
		});
		expect((await DatabaseService.getConversation(conversation.id))?.knowledgeConnected).toBe(false);
		await DatabaseService.updateConversation(conversation.id, {
			knowledgeConnected: true, knowledgeDocuments: history.knowledgeDocuments
		});
		expect((await DatabaseService.getConversation(conversation.id))?.knowledgeDocuments).toEqual([{ id: 'fixture-document', name: 'Fixture.txt' }]);
		expect((await DatabaseService.getConversationMessages(conversation.id))[0].routing?.decision?.request_id).toBe('fixture-request');
	});
});
