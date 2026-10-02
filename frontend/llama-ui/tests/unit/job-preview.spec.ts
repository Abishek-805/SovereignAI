import { describe, expect, it } from 'vitest';
import { runningJobPreview, jobPreviewContent } from '../../src/lib/services/job-preview.service';

describe('runningJobPreview', () => {
	it('displays only actual accumulated public answer text', () => {
		expect(runningJobPreview({ state: 'running', partial_kind: 'answer', partial_answer: 'The measured value is ' }))
			.toEqual({ kind: 'answer', text: 'The measured value is ' });
	});
	it('keeps generated code separate from answer text and names its path', () => {
		expect(runningJobPreview({ state: 'running', partial_kind: 'code', partial_path: 'main.py', partial_answer: 'print(' }))
			.toEqual({ kind: 'code', path: 'main.py', text: 'print(' });
	});
	it('does not expose planner output, an empty draft, or terminal job text', () => {
		expect(runningJobPreview({ state: 'running', partial_answer: '{"action":"edit_code"}' })).toBeNull();
		expect(runningJobPreview({ state: 'running', partial_kind: 'answer', partial_answer: '' })).toBeNull();
		expect(runningJobPreview({ state: 'completed', partial_kind: 'answer', partial_answer: 'draft' })).toBeNull();
		expect(runningJobPreview({ state: 'cancelled', partial_kind: 'answer', partial_answer: 'draft' })).toBeNull();
	});
});


describe('jobPreviewContent', () => {
    it('leaves public answers unchanged', () => {
        expect(jobPreviewContent({ kind: 'answer', text: 'Hello' })).toBe('Hello');
    });
    it('renders generated code without letting embedded fences escape the code block', () => {
        expect(jobPreviewContent({ kind: 'code', text: 'print("```example")' }))
            .toBe('````\nprint("```example")\n````');
    });
});
