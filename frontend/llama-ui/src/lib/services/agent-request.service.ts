/** The agent endpoint accepts eight history entries: four user/assistant pairs. */
export function agentConversationHistory(
	turns: ReadonlyArray<{ instruction: string; answer?: string; state: string }>
): string[] {
	return turns
		.filter((turn) => ['answered', 'completed'].includes(turn.state))
		.slice(-4)
		.flatMap((turn) => [
			`User: ${turn.instruction.slice(0, 1000)}`,
			// Keep conversational context without replaying a whole evidence report
			// or artifact body as the instruction for the next task.
			...(turn.answer ? [`Assistant: ${turn.answer.slice(0, 500)}`] : [])
		]);
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
