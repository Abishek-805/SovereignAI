import { describe, expect, it } from 'vitest';
import { CHAT_ATTACHMENT_CHAR_LIMIT, limitChatAttachment } from '../../src/lib/utils/chat-attachment-limit';

describe('local chat attachment limit', () => {
	it('preserves short attachments', () => {
		expect(limitChatAttachment('short')).toEqual({ text: 'short', truncated: false, used: 5 });
	});

	it('marks a long attachment as an excerpt and points to Documents', () => {
		const result = limitChatAttachment('A'.repeat(CHAT_ATTACHMENT_CHAR_LIMIT + 10));
		expect(result.truncated).toBe(true);
		expect(result.text).toContain('Import the full file in Documents');
		expect(result.text.startsWith('A'.repeat(CHAT_ATTACHMENT_CHAR_LIMIT) + '\n[')).toBe(true);
		expect(result.used).toBe(CHAT_ATTACHMENT_CHAR_LIMIT);
	});

	it('can share a fixed budget across multiple files', () => {
		const first = limitChatAttachment('A'.repeat(3000), CHAT_ATTACHMENT_CHAR_LIMIT);
		const second = limitChatAttachment('B'.repeat(3000), CHAT_ATTACHMENT_CHAR_LIMIT - first.used);
		expect(second.used).toBe(1000);
		expect(second.truncated).toBe(true);
	});
});
