import { describe, it, expect } from 'vitest';
import { removedDuplicateGroups } from '../../src/lib/services/duplicate-audit';
describe('actual duplicate audit',()=>{
 it('does not invent removed names from summary or read-only scans',()=>{
  expect(removedDuplicateGroups(undefined)).toEqual([]);
  expect(removedDuplicateGroups([{tool:'document_duplicates',result:{removed_count:2,groups:[]}}])).toEqual([]);
 });
 it('preserves actual retained and removed identities',()=>{
  const kept={document_id:'a',display_name:'Original.pdf'},duplicate={document_id:'b',display_name:'Copy.pdf'};
  expect(removedDuplicateGroups([{tool:'document_deduplicate',result:{removed_count:1,groups:[{kept,duplicates:[duplicate,null]}]}}])).toEqual([{kept,removed:[duplicate]}]);
 });
});
