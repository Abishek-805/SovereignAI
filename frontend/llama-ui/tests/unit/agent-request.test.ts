import { afterEach, describe, expect, it, vi } from 'vitest';
import { agentConversationHistory, agentGoalError, agentProblem, agentRequest, createJobAdmission, decodeAgentResponse } from '$lib/services/agent-request.service';

it('explains agent failures without a raw Error prefix', () => {
	expect(agentProblem('Error: That Knowledge source already exists')).toContain('already exists');
	expect(agentProblem('Error: The current request does not authorize document create. Specify the operation and its target.')).toContain('Please');
	expect(agentProblem('Error: Unexpected runtime failure')).not.toMatch(/^Error:/);
	expect(agentProblem('Error: Local model timed out; inspect its status and retry')).toContain('two minutes');
});

afterEach(() => vi.unstubAllGlobals());

describe('Code assistant request contract', () => {
	it('keeps the newest four successful exchanges within the eight-entry API limit', () => {
		const turns = Array.from({ length: 30 }, (_, index) => ({
			instruction: `Question ${index}`,
			answer: `Reply ${index}`,
			state: 'answered'
		}));
		const snapshot = structuredClone(turns);
		expect(agentConversationHistory(turns)).toEqual(
			[26, 27, 28, 29].flatMap((index) => [`User: Question ${index}`, `Assistant: Reply ${index}`])
		);
		expect(turns).toEqual(snapshot);
	});

	it('keeps a failed user request for follow-up references without replaying its error', () => {
		expect(agentConversationHistory([
			{ instruction: 'hello', answer: 'A real reply', state: 'answered' },
			{ instruction: 'old request', answer: 'Error: Request failed', state: 'failed' },
			{ instruction: 'cancelled edit', state: 'stopped' },
			{ instruction: 'current question', state: 'running' }
		])).toEqual(['User: hello', 'Assistant: A real reply', 'User: old request', 'Assistant: Task failed.']);
	});

	it('posts bounded history and returns the actual job ID', async () => {
		const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ job_id: 'job-1' })));
		vi.stubGlobal('fetch', fetchMock);
		const history = agentConversationHistory(Array.from({ length: 6 }, () => ({
			instruction: 'hello', answer: 'reply', state: 'answered'
		})));
		expect(await agentRequest('/agent/jobs', { goal: 'how are you?', document_ids: [], history }))
			.toEqual({ job_id: 'job-1' });
		const payload = JSON.parse(fetchMock.mock.calls[0][1].body);
		expect(payload.history).toHaveLength(8);
		expect(payload.goal).toBe('how are you?');
	});
	it('bounds prior evidence narratives without changing the next task or mutating history', () => {
		const turns = [{ instruction: 'Compare reports', answer: 'x'.repeat(12000), state: 'answered' }];
		expect(agentConversationHistory(turns)).toEqual(['User: Compare reports', 'Assistant: ' + 'x'.repeat(500)]);
		expect(turns[0].answer).toHaveLength(12000);
	});

	it('shows the rejected field and backend validation reason', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
			detail: [{ loc: ['body', 'history'], msg: 'List should have at most 8 items' }]
		}), { status: 422 })));
		await expect(agentRequest('/agent/jobs', {}))
			.rejects.toThrow('history: List should have at most 8 items');
	});

	it('preserves actionable workbench errors', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
			message: 'Another model task is running'
		}), { status: 409 })));
		await expect(agentRequest('/agent/jobs', {})).rejects.toThrow('Another model task is running');
	});

	it('allows the maximum goal and rejects overlong instructions before admission', () => {
		expect(agentGoalError('x'.repeat(2000))).toBeNull();
		expect(agentGoalError('x'.repeat(2001))).toContain('2,000');
		expect(agentGoalError('   ')).toContain('Enter');
	});

	it('queues cancellation until the new request has an ID and never targets the prior job', async () => {
		const stop = vi.fn().mockResolvedValue(undefined);
		const previous = createJobAdmission(stop);
		await previous.admit('previous-job');
		const pending = createJobAdmission(stop);
		await pending.requestStop();
		expect(stop).not.toHaveBeenCalled();
		await pending.admit('new-job');
		await pending.requestStop();
		expect(stop.mock.calls).toEqual([['new-job']]);
	});

	it('cancels an admitted request directly', async () => {
		const stop = vi.fn().mockResolvedValue(undefined);
		const pending = createJobAdmission(stop);
		await pending.admit('current-job');
		expect(stop).not.toHaveBeenCalled();
		await pending.requestStop();
		expect(stop).toHaveBeenCalledExactlyOnceWith('current-job');
	});

	it('shares useful validation decoding with multipart and knowledge requests', async () => {
		await expect(decodeAgentResponse(new Response(JSON.stringify({ detail: 'Select at most 100 documents' }), { status: 422 })))
			.rejects.toThrow('Select at most 100 documents');
	});
});
