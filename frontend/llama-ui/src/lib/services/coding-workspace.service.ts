import { apiFetch } from '$lib/utils/api-fetch';
import { getAuthHeaders } from '$lib/utils/api-headers';
import { base } from '$app/paths';

export type WorkspaceFile = { name: string; bytes: number; sha256?: string };
export type CodingWorkspace = {
	workspace_id: string;
	name: string;
	host_path?: string;
	created_at: number;
	files: WorkspaceFile[];
	folders?: string[];
};
export type ToolEvent = {
	event: string;
	detail?: string;
	file?: string;
	files?: string[];
	attempt?: number;
	exit_code?: number;
	checks?: Record<string, boolean>;
};
export type CodingTask = {
	task_id: string;
	workspace_id: string;
	target: string;
	state: 'running' | 'completed' | 'failed' | 'undone';
	attempts: number;
	events: ToolEvent[];
	checks: Record<string, boolean>;
	diff: string;
	instruction?: string;
	changes?: Array<{ action: 'create' | 'edit' | 'delete' | 'mkdir' | 'rmdir'; path: string; before: string | null; after: string | null }>;
	original_content?: string;
	applied_hash?: string;
	stdout: string;
	stderr: string;
	output_files: Array<{ name: string; bytes: number; sha256: string; url: string }>;
	routing: { capability: string; model: string; reason?: string };
	sandbox: { backend: string; image_id: string | null };
	error?: string;
};

export class CodingWorkspaceService {
	static list(): Promise<CodingWorkspace[]> {
		return apiFetch('/coding/workspaces');
	}

	static create(name: string): Promise<CodingWorkspace> {
		return apiFetch('/coding/workspaces', { method: 'POST', body: JSON.stringify({ name }) });
	}

	static get(id: string): Promise<CodingWorkspace> {
		return apiFetch('/coding/workspaces/' + encodeURIComponent(id));
	}

	static read(id: string, name: string): Promise<{ name: string; content: string; sha256: string; bytes?: number; binary?: boolean; editable?: boolean }> {
		return apiFetch('/coding/workspaces/' + encodeURIComponent(id) + '/files/' + encodeURIComponent(name));
	}

	static importFile(id:string, name:string, file:File): Promise<WorkspaceFile & {sha256:string}> {
		return apiFetch('/coding/workspaces/'+encodeURIComponent(id)+'/import-files/'+encodeURIComponent(name), {
			method:'POST', authOnly:true, headers:{'Content-Type':'application/octet-stream'}, body:file
		});
	}

	static async asset(id:string,name:string): Promise<Blob> {
		const response=await fetch(base+'/coding/workspaces/'+encodeURIComponent(id)+'/assets/'+encodeURIComponent(name),{headers:getAuthHeaders()});
		if(!response.ok)throw new Error('Cannot load this project asset ('+response.status+')');
		return response.blob();
	}

	static write(id: string, name: string, content: string, expectedSha256?: string): Promise<WorkspaceFile & { sha256: string }> {
		return apiFetch('/coding/workspaces/' + encodeURIComponent(id) + '/files/' + encodeURIComponent(name), {
			method: 'PUT',
			body: JSON.stringify({ content, ...(expectedSha256 !== undefined ? { expected_sha256: expectedSha256 } : {}) })
		});
	}

	static fileOperation(id: string, action: 'copy' | 'move' | 'delete' | 'mkdir', source: string, destination?: string): Promise<{ workspace: CodingWorkspace }> {
		return apiFetch('/coding/workspaces/' + encodeURIComponent(id) + '/file-operation', {
			method: 'POST',
			body: JSON.stringify({ action, source, destination })
		});
	}

	static openVSCode(id:string): Promise<{path:string}> {
		return apiFetch('/coding/workspaces/'+encodeURIComponent(id)+'/open-vscode',{method:'POST'});
	}

	static reveal(id:string): Promise<{path:string}> {
		return apiFetch('/coding/workspaces/'+encodeURIComponent(id)+'/reveal',{method:'POST'});
	}

	static run(id: string, target: string, instruction: string): Promise<CodingTask> {
		return apiFetch('/coding/workspaces/' + encodeURIComponent(id) + '/tasks', {
			method: 'POST',
			body: JSON.stringify({ target, instruction })
		});
	}

	static undo(id: string, taskId: string): Promise<CodingTask> {
		return apiFetch('/coding/workspaces/' + encodeURIComponent(id) + '/tasks/' + encodeURIComponent(taskId) + '/undo', { method: 'POST' });
	}
}
