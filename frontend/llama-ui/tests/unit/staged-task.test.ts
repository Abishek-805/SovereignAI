import {describe,it,expect} from 'vitest';
import {stagedTaskFromResponse} from '../../src/lib/services/staged-task';
describe('reviewable task discovery',()=>{
 it('discovers deletion drafts through the application result contract',()=>{
  const task={state:'completed',publication_state:'staged',task_id:'delete',changes:[{action:'delete',path:'image.png',after:null}]};
  expect(stagedTaskFromResponse({result:{operations:[{tool:'file_organization',result:task}]}})).toBe(task);
 });
 it('does not turn a successful query into a file change',()=>{
  expect(stagedTaskFromResponse({result:{state:'completed',answer:'3'}})).toBeUndefined();
 });
});
