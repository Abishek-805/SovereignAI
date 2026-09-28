import { describe, it, expect } from 'vitest';
import { acceptedEditorContent } from '$lib/services/accepted-editor-state';

describe('Accepting persisted agent changes', () => {
 it('replaces the stale empty pre-generation editor when leaving review', () => {
  const generated = 'def divide(a, b):\n    return a / b\n';
  expect(acceptedEditorContent({ reviewing: true, draft: '', saved: '', disk: generated }))
   .toEqual({ content: generated, baseline: generated });
 });
 it('does not restore an old cached draft after reviewing an edit', () => {
  expect(acceptedEditorContent({ reviewing: true, draft: 'old code', saved: 'old code', disk: 'new code' }))
   .toEqual({ content: 'new code', baseline: 'new code' });
 });
 it('retains deliberate unsaved edits made in the editable source view', () => {
  expect(acceptedEditorContent({ reviewing: false, draft: 'user edit', saved: 'agent edit', disk: 'agent edit' }))
   .toEqual({ content: 'user edit', baseline: 'agent edit' });
 });
 it('loads an accepted new file that has no cached baseline', () => {
  expect(acceptedEditorContent({ reviewing: false, draft: '', saved: undefined, disk: 'created' }))
   .toEqual({ content: 'created', baseline: 'created' });
 });
});
