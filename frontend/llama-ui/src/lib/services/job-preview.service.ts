/** A running job may expose real, accumulated output from the local model.
 * It is a display-only draft; only the terminal job result is authoritative. */
export type JobPreview = { kind: 'answer' | 'code'; text: string; path?: string };

export function runningJobPreview(job: unknown): JobPreview | null {
	if (!job || typeof job !== 'object') return null;
	const snapshot = job as Record<string, unknown>;
	if (snapshot.state !== 'running') return null;
	if (snapshot.partial_kind !== 'answer' && snapshot.partial_kind !== 'code') return null;
	if (typeof snapshot.partial_answer !== 'string' || !snapshot.partial_answer) return null;
	return {
		kind: snapshot.partial_kind,
		text: snapshot.partial_answer,
		...(snapshot.partial_kind === 'code' && typeof snapshot.partial_path === 'string'
			? { path: snapshot.partial_path }
			: {})
	};
}

/** Keep code as code even when the generated source contains Markdown fences. */
export function jobPreviewContent(preview: JobPreview): string {
    if (preview.kind === 'answer') return preview.text;
    const runs = preview.text.match(/`+/g) || [];
    const fence = '`'.repeat(Math.max(3, ...runs.map(run => run.length + 1)));
    return fence + '\n' + preview.text + '\n' + fence;
}
