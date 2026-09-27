import { apiFetch } from '$lib/utils/api-fetch';

export type WorkbenchInfo = {
	runtime: {
		busy: boolean;
		documents: number;
		generator: { available?: boolean; alias?: string; is_sleeping?: boolean; message?: string };
	};
	models: Array<{
		capability: string; alias: string; model_id: string; quantization: string;
		context: number; runtime: string; observed_gpu_mib: number | null; enabled: boolean; assets_present: boolean;
	}>;
	routing: { mode: 'automatic'; routes: Record<string, { capability: string | null; model: string | null }> };
	sandbox: {
		ready: boolean; reason: string | null; image_id: string | null;
		policy: {
			backend: string; network: string; user: string; filesystem: string;
			cpus: number; memory_mb: number; timeout_seconds: number;
			privileged: boolean; docker_socket: boolean;
		};
	};
	tools: Array<{ name: string; available: boolean }>;
	host: string;
	network_proof: string;
};

export type ArtifactEntry = {
	name: string; task_id: string; created_at: string | number | null;
	kind: string; validated: boolean; url: string | null;
};

export class WorkbenchService {
	static info(): Promise<WorkbenchInfo> { return apiFetch('/workbench/info'); }
	static artifacts(): Promise<ArtifactEntry[]> { return apiFetch('/workbench/artifacts'); }
}
