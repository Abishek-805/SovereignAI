import { describe, it, expect, vi, beforeEach } from 'vitest';
const db = vi.hoisted(() => ({
	getAllConversations: vi.fn(),
	createConversation: vi.fn(),
	createRootMessage: vi.fn(),
	createMessageBranch: vi.fn(),
	updateConversation: vi.fn()
}));
vi.mock('$lib/services/database.service', () => ({ DatabaseService: db }));
import { migrateKnowledgeHistory } from '$lib/services/knowledge-history.service';
describe('Former Knowledge chat migration', () => {
	let saved: Record<string, string>;
	beforeEach(() => {
		vi.clearAllMocks();
		saved = {};
		vi.stubGlobal('localStorage', { getItem: (key: string) => saved[key] ?? null });
		db.getAllConversations.mockResolvedValue([]);
		db.createConversation.mockResolvedValue({ id: 'conversation' });
		db.createRootMessage.mockResolvedValue('root');
		db.createMessageBranch.mockImplementation(async (message) => ({
			...message,
			id: message.role === 'user' ? 'user' : 'assistant'
		}));
		db.updateConversation.mockResolvedValue(undefined);
	});
	it('preserves questions, source identities and artifact URLs in normal history', async () => {
		const source = {
			label: 'S1',
			document_id: 'document',
			chunk_id: 'chunk',
			display_name: 'Manual.pdf',
			page: 2,
			text: 'Evidence'
		};
		saved['sovereign-knowledge-history'] = JSON.stringify([
			{
				id: 'legacy',
				title: 'Original title',
				updatedAt: 42,
				turns: [
					{
						question: 'Explain the manual',
						result: {
							status: 'answered',
							answer: 'Grounded answer',
							sources: [source],
							downloads: { word: '/real.docx' }
						}
					}
				]
			}
		]);
		await migrateKnowledgeHistory();
		expect(db.createConversation).toHaveBeenCalledWith('Original title');
		expect(db.createMessageBranch.mock.calls[0][0].content).toBe('Explain the manual');
		expect(db.createMessageBranch.mock.calls[1][0]).toMatchObject({
			content: 'Grounded answer',
			knowledgeSources: [source],
			knowledgeDownloads: { word: '/real.docx' }
		});
		expect(db.updateConversation).toHaveBeenCalledWith('conversation', {
			legacyKnowledgeChatId: 'legacy',
			lastModified: 42
		});
		expect(saved['sovereign-knowledge-history']).toContain('Grounded answer');
	});
	it('does not duplicate already imported history', async () => {
		saved['sovereign-knowledge-history'] = JSON.stringify([{ id: 'legacy', turns: [] }]);
		db.getAllConversations.mockResolvedValue([{ legacyKnowledgeChatId: 'legacy' }]);
		await migrateKnowledgeHistory();
		expect(db.createConversation).not.toHaveBeenCalled();
	});
	it('keeps the original history when persistence fails', async () => {
		saved['sovereign-knowledge-history'] = JSON.stringify([
			{ id: 'legacy', turns: [{ question: 'Question', result: { answer: 'Answer' } }] }
		]);
		db.createMessageBranch.mockRejectedValue(new Error('Storage unavailable'));
		await expect(migrateKnowledgeHistory()).rejects.toThrow('Storage unavailable');
		expect(saved['sovereign-knowledge-history']).toContain('Answer');
		expect(db.updateConversation).not.toHaveBeenCalled();
	});
	it('ignores malformed sessions without generating fake conversations', async () => {
		saved['sovereign-knowledge-history'] = JSON.stringify([
			{ turns: [] },
			{ id: 'invalid', turns: 'bad' }
		]);
		await migrateKnowledgeHistory();
		expect(db.createConversation).not.toHaveBeenCalled();
	});
});
