/** The agent endpoint accepts eight history entries: four user/assistant pairs. */
export function agentConversationHistory(
	turns: ReadonlyArray<{ instruction: string; answer?: string; state: string }>
): string[] {
	return turns
		.filter((turn) => ['answered', 'completed', 'failed'].includes(turn.state))
		.slice(-4)
		.flatMap((turn) => [
			`User: ${turn.instruction.slice(0, 1000)}`,
			// Keep conversational context without replaying a whole evidence report
			// or artifact body as the instruction for the next task.
			...(turn.state === 'failed' ? ['Assistant: Task failed.'] : turn.answer ? [`Assistant: ${turn.answer.slice(0, 500)}`] : [])
		]);
}

export function agentProblem(problem: unknown): string {
	const message = String(problem).replace(/^Error:\s*/i, '').trim();
	if (/does not authorize/i.test(message))
		return 'I could not confirm the requested file change. Please say what to create or update and, if you have a specific file in mind, name it.';
	if (/Knowledge source already exists|Knowledge document named .* already exists/i.test(message))
		return 'A Knowledge file with that name already exists. Please ask me to update it or give the new file a different name.';
	if (/Name one unique Knowledge document/i.test(message))
		return 'I found more than one possible Knowledge file. Please name the file you want me to change.';
	if (/Local model timed out/i.test(message))
		return 'The local model did not respond within two minutes. Please try again or check its status in Control Center.';
	if (/invalid or incomplete code|invalid application operations/i.test(message))
		return 'The local model returned an incomplete change, so I could not apply this task. Please try a shorter, more specific request.';
	return message ? `I could not finish this task: ${message}` : 'I could not finish this task. Please try again.';
}

/** Keep backend validation details visible instead of hiding them as Request failed. */
export async function agentRequest(url: string, body?: unknown) {
	const response = await fetch(
		url,
		body === undefined
			? {}
			: {
					method: 'POST',
					headers: { 'content-type': 'application/json' },
					body: JSON.stringify(body)
				}
	);
	return decodeAgentResponse(response);
}

export async function decodeAgentResponse(response: Response) {
	const data = await response.json();
	if (!response.ok) {
		const detail = Array.isArray(data.detail)
			? data.detail
					.map((error: { loc?: unknown[]; msg?: string }) =>
						`${(error.loc || []).filter((part) => part !== 'body').join('.')}: ${error.msg || 'Invalid value'}`
					)
					.join('; ')
			: typeof data.detail === 'string'
				? data.detail
				: '';
		throw new Error(data.message || detail || `Request failed (${response.status})`);
	}
	return data;
}

export function agentGoalError(goal: string): string | null {
	if (!goal.trim()) return 'Enter a question or task.';
	if (goal.length > 2000) return 'Keep the question or task under 2,000 characters.';
	return null;
}

/** Cancellation can arrive before the server assigns this request a job ID. */
export function createJobAdmission(stop: (jobId: string) => Promise<unknown>) {
	let admittedId = '';
	let stopRequested = false;
	let stopRequest: Promise<unknown> | undefined;
	function sendStop() {
		if (admittedId && !stopRequest) stopRequest = stop(admittedId);
		return stopRequest;
	}
	return {
		async requestStop() {
			stopRequested = true;
			await sendStop();
		},
		async admit(jobId: string) {
			admittedId = jobId;
			if (stopRequested) await sendStop();
		}
	};
}
