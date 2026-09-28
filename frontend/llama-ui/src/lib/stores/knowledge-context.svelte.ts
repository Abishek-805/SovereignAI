import { conversationsStore } from './conversations/index.svelte';
import { DatabaseService } from '$lib/services/database.service';
import { KnowledgeService, type KnowledgeReference } from '$lib/services/knowledge.service';
export type KnowledgeScope = 'all' | 'selected';
class KnowledgeContext {
	pending = $state<KnowledgeReference[]>([]);
	agent = $state<KnowledgeReference[]>([]);
	catalog = $state<KnowledgeReference[]>([]);
	pendingConnected = $state(true);
	pendingScope = $state<KnowledgeScope>('all');
	agentConnected = $state(true);
	agentScope = $state<KnowledgeScope>('all');
	pickerOpen = $state(false);
	private restored = false;
	restorePending() {
		if (this.restored || typeof localStorage === 'undefined') return;
		this.restored = true;
		try {
			const saved = JSON.parse(localStorage.getItem('sovereign-chat-knowledge-options') || '{}');
			this.pendingConnected = typeof saved.connected === 'boolean' ? saved.connected : true;
			this.pendingScope = saved.scope === 'selected' ? 'selected' : 'all';
			this.pending = Array.isArray(saved.documents)
				? saved.documents.filter(
						(doc: unknown): doc is KnowledgeReference => typeof doc === 'object' && doc !== null && 'id' in doc && 'name' in doc && typeof doc.id === 'string' && typeof doc.name === 'string'
					)
				: [];
		} catch {}
	}
	get connected() {
		return conversationsStore.activeConversation?.knowledgeConnected ?? this.pendingConnected;
	}
	get scope(): KnowledgeScope {
		return conversationsStore.activeConversation?.knowledgeScope ?? this.pendingScope;
	}
	get documents(): KnowledgeReference[] {
		return this.scope === 'all'
			? this.catalog
			: (conversationsStore.activeConversation?.knowledgeDocuments ?? this.pending);
	}
	async refresh() {
		this.catalog = (await KnowledgeService.list()).map((doc) => ({
			id: doc.document_id,
			name: doc.display_name
		}));
	}
	async resolve(target: 'chat' | 'agent') {
		if (!(target === 'chat' ? this.connected : this.agentConnected)) return [];
		const scope = target === 'chat' ? this.scope : this.agentScope;
		if (scope === 'all') await this.refresh();
		const documents =
			scope === 'all' ? this.catalog : target === 'chat' ? this.documents : this.agent;
		if (documents.length > 256)
			throw new Error(
				'This request can connect up to 256 documents. Choose a smaller Knowledge scope.'
			);
		return scope === 'all' ? this.catalog : target === 'chat' ? this.documents : this.agent;
	}
	async configure(
		connected: boolean,
		scope: KnowledgeScope = this.scope,
		documents: KnowledgeReference[] = this.documents
	) {
		// Read primitive reference fields into fresh records; selected documents may be reactive.
		const unique = [...new Map(documents.map((doc) => [doc.id, { id: doc.id, name: doc.name }])).values()];
		this.pendingConnected = connected;
		this.pendingScope = scope;
		this.pending = unique;
		if (typeof localStorage !== 'undefined')
			localStorage.setItem(
				'sovereign-chat-knowledge-options',
				JSON.stringify({ connected, scope, documents: unique })
			);
		const conversation = conversationsStore.activeConversation;
		if (conversation) {
			const change = {
				knowledgeConnected: connected,
				knowledgeScope: scope,
				knowledgeDocuments: unique
			};
			await DatabaseService.updateConversation(conversation.id, change);
			conversationsStore.applyConversationUpdate(conversation.id, change);
		}
	}
	async set(documents: KnowledgeReference[], scope: KnowledgeScope = 'selected') {
		await this.configure(true, scope, documents);
	}
	setAgent(documents: KnowledgeReference[], scope: KnowledgeScope = 'selected') {
		this.agent = documents;
		this.agentScope = scope;
		this.agentConnected = true;
	}
}
export const knowledgeContext = new KnowledgeContext();
