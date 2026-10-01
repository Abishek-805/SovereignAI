import { describe, expect, it } from 'vitest';
import { nextMatchIndex, tableFindParams, workspaceDeletionBlocked, pendingFileChange } from '$lib/services/workspace-ui-state';
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

describe('staged file review navigation', () => {
 const changes = [
  {path:'web/index.html',action:'edit',before:'old html',after:'new html'},
  {path:'web/style.css',action:'edit',before:'old css',after:'new css'},
  {path:'empty.txt',action:'create',before:null,after:''},
  {path:'removed.py',action:'delete',before:'print(1)',after:null},
  {path:'web',action:'mkdir',before:null,after:null}
 ];
 const task = {state:'completed',publication_state:'staged',changes};
 it('selects each changed tab independently, including empty creations and deletions', () => {
  expect(pendingFileChange(task,'web/index.html')?.after).toBe('new html');
  expect(pendingFileChange(task,'web/style.css')?.after).toBe('new css');
  expect(pendingFileChange(task,'empty.txt')?.before).toBeNull();
  expect(pendingFileChange(task,'empty.txt')?.after).toBe('');
  expect(pendingFileChange(task,'removed.py')?.after).toBeNull();
 });
 it('opens unchanged files normally and never reviews published or failed tasks', () => {
  expect(pendingFileChange(task,'other.py')).toBeUndefined();
  expect(pendingFileChange(task,'web')).toBeUndefined();
  expect(pendingFileChange({...task,publication_state:'published'},'web/style.css')).toBeUndefined();
  expect(pendingFileChange({...task,state:'failed'},'web/style.css')).toBeUndefined();
 });
});
