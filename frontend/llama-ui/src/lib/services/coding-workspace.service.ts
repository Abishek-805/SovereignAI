import { apiFetch } from '$lib/utils/api-fetch';

export type WorkspaceFile = { name: string; bytes: number };
export type CodingWorkspace = {
	workspace_id: string;
	name: string;
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

	static read(id: string, name: string): Promise<{ name: string; content: string }> {
		return apiFetch('/coding/workspaces/' + encodeURIComponent(id) + '/files/' + encodeURIComponent(name));
	}

	static write(id: string, name: string, content: string): Promise<WorkspaceFile> {
		return apiFetch('/coding/workspaces/' + encodeURIComponent(id) + '/files/' + encodeURIComponent(name), {
			method: 'PUT',
			body: JSON.stringify({ content })
		});
	}

	static fileOperation(id: string, action: 'copy' | 'move' | 'delete' | 'mkdir', source: string, destination?: string): Promise<{ workspace: CodingWorkspace }> {
		return apiFetch('/coding/workspaces/' + encodeURIComponent(id) + '/file-operation', {
			method: 'POST',
			body: JSON.stringify({ action, source, destination })
		});
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
