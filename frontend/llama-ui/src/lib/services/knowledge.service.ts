import { decodeAgentResponse } from './agent-request.service';
export interface KnowledgeDocument {
	document_id: string;
	display_name: string;
	chunk_count: number;
	folder?: string;
	source_extension?: string;
	active_hash?: string;
	warnings?: string[];
 indexing_status?: 'indexing'|'indexed'|'failed';
}
export interface KnowledgeReference {
	id: string;
	name: string;
}
export interface KnowledgeSource {
	label: string;
	display_name: string;
	document_id?: string;
	page?: number | null;
	chunk_id: string;
	text: string;
}
export async function knowledgeJson(response: Response) {
	return decodeAgentResponse(response);
}
export const KnowledgeService = {
	list: async (): Promise<KnowledgeDocument[]> => knowledgeJson(await fetch('/documents')),
	open(id: string, page?: number | null, chunk?: string) {
		window.dispatchEvent(
			new CustomEvent('sovereign-open-workspace', {
				detail: {
					tab: 'knowledge',
					documentId: id,
					page,
					chunk
				}
			})
		);
	},
	connect(target: 'chat' | 'agent', documents: KnowledgeReference[]) {
		window.dispatchEvent(
			new CustomEvent('sovereign-connect-knowledge', { detail: { target, documents } })
		);
		window.dispatchEvent(
			target === 'chat'
				? new Event('sovereign-close-workspace')
				: new CustomEvent('sovereign-open-workspace', { detail: { tab: 'agent' } })
		);
	}
};

export interface KnowledgeCoverage {
	requested_documents: number;
	covered_documents: number;
	all_indexed_passages_included: boolean;
	documents: { display_name: string; included_passages: number; indexed_passages: number }[];
}
