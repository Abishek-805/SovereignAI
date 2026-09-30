import { describe, expect, it } from 'vitest';
import { nextMatchIndex, tableFindParams, workspaceDeletionBlocked } from '$lib/services/workspace-ui-state';
describe('table Find navigation', () => {
 it('wraps previous and next over every stored match', () => {
  expect(nextMatchIndex(199, 1, 301)).toBe(200);
  expect(nextMatchIndex(300, 1, 301)).toBe(0);
  expect(nextMatchIndex(0, -1, 301)).toBe(300);
 });
 it('sends literal text, options and sheet scope to the server', () => {
  const params = tableFindParams('A&B +', true, true, 200, 2);
  expect(params.get('q')).toBe('A&B +');
  expect(params.get('match_case')).toBe('true');
  expect(params.get('whole_cell')).toBe('true');
  expect(params.get('sheet')).toBe('2');
  expect(params.get('offset')).toBe('200');
  expect(tableFindParams('x', false, false, 0).has('sheet')).toBe(false);
 });
});
describe('workspace deletion protection', () => {
 it('protects unsaved editor content before draft synchronization', () => {
  expect(workspaceDeletionBlocked('active','active',false,true,false)).toBe(true);
 });
 it('protects jobs and staged drafts but permits unrelated projects', () => {
  expect(workspaceDeletionBlocked('active','active',true,false,false)).toBe(true);
  expect(workspaceDeletionBlocked('active','active',false,false,true)).toBe(true);
  expect(workspaceDeletionBlocked('other','active',true,true,true)).toBe(false);
 });
});
