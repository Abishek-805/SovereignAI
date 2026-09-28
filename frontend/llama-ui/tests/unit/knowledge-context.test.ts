import { beforeEach, describe, expect, it, vi } from 'vitest';
const state=vi.hoisted(()=>({activeConversation:null as null|{id:string;knowledgeConnected?:boolean;knowledgeScope?:'all'|'selected';knowledgeDocuments?:{id:string;name:string}[]},applyConversationUpdate:vi.fn()}));
const db=vi.hoisted(()=>({updateConversation:vi.fn()}));
const library=vi.hoisted(()=>({list:vi.fn()}));
vi.mock('$lib/stores/conversations/index.svelte',()=>({conversationsStore:state}));
vi.mock('$lib/services/database.service',()=>({DatabaseService:db}));
vi.mock('$lib/services/knowledge.service',()=>({KnowledgeService:library}));
import { knowledgeContext } from '$lib/stores/knowledge-context.svelte';
describe('Knowledge connection and scope',()=>{
 beforeEach(()=>{vi.clearAllMocks();state.activeConversation=null;state.applyConversationUpdate.mockImplementation((_id,change)=>Object.assign(state.activeConversation!,change));knowledgeContext.pending=[];knowledgeContext.pendingConnected=true;knowledgeContext.pendingScope='all';knowledgeContext.catalog=[];knowledgeContext.agent=[];knowledgeContext.agentConnected=true;knowledgeContext.agentScope='all';library.list.mockResolvedValue([{document_id:'one',display_name:'One.txt'}]);});
 it('defaults connected to all documents and includes newly imported documents on next request',async()=>{
  expect(knowledgeContext.connected).toBe(true);expect(knowledgeContext.scope).toBe('all');
  expect(await knowledgeContext.resolve('chat')).toEqual([{id:'one',name:'One.txt'}]);
  library.list.mockResolvedValue([{document_id:'one',display_name:'One.txt'},{document_id:'two',display_name:'Two.txt'}]);
  expect((await knowledgeContext.resolve('chat')).map(doc=>doc.id)).toEqual(['one','two']);
 });
 it('persists off and never reads library while disconnected',async()=>{
  state.activeConversation={id:'chat'};await knowledgeContext.configure(false);
  expect(db.updateConversation).toHaveBeenCalledWith('chat',expect.objectContaining({knowledgeConnected:false}));
  expect(await knowledgeContext.resolve('chat')).toEqual([]);expect(library.list).not.toHaveBeenCalled();
 });
 it('copies reactive document references into cloneable records when toggling an existing chat',async()=>{
  const document=new Proxy({id:'one',name:'One.txt'},{});
  state.activeConversation={id:'chat',knowledgeConnected:true,knowledgeScope:'selected',knowledgeDocuments:[document]};
  db.updateConversation.mockImplementation(async(_id,change)=>{structuredClone(change);});
  await knowledgeContext.configure(false);
  expect(state.activeConversation.knowledgeConnected).toBe(false);
  expect(db.updateConversation.mock.calls[0][1].knowledgeDocuments).toEqual([{id:'one',name:'One.txt'}]);
  await knowledgeContext.configure(true);
  expect(await knowledgeContext.resolve('chat')).toEqual([{id:'one',name:'One.txt'}]);
 });
 it('selected scope survives disconnection and reconnection without silently adding other documents',async()=>{
  state.activeConversation={id:'chat'};await knowledgeContext.set([{id:'one',name:'One.txt'}]);
  await knowledgeContext.configure(false);expect(await knowledgeContext.resolve('chat')).toEqual([]);
  await knowledgeContext.configure(true);expect(await knowledgeContext.resolve('chat')).toEqual([{id:'one',name:'One.txt'}]);expect(library.list).not.toHaveBeenCalled();
 });
 it('persists pending Off before the first conversation exists',async()=>{
  const values:Record<string,string>={};vi.stubGlobal('localStorage',{getItem:(key:string)=>values[key]||null,setItem:(key:string,value:string)=>values[key]=value});
  await knowledgeContext.configure(false);knowledgeContext.pendingConnected=true;knowledgeContext.restorePending();
  expect(knowledgeContext.connected).toBe(false);vi.unstubAllGlobals();
 });
 it('agent respects all, selected and off independently from Chat',async()=>{
  expect(await knowledgeContext.resolve('agent')).toEqual([{id:'one',name:'One.txt'}]);
  knowledgeContext.setAgent([{id:'two',name:'Two.txt'}]);expect(await knowledgeContext.resolve('agent')).toEqual([{id:'two',name:'Two.txt'}]);
  knowledgeContext.agentConnected=false;expect(await knowledgeContext.resolve('agent')).toEqual([]);expect(knowledgeContext.connected).toBe(true);
 });
});
