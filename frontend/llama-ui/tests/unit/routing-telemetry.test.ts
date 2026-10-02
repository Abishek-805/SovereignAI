import { describe, expect, it } from 'vitest';
import { routeFacts, routingModel } from '../../src/lib/services/routing-telemetry';
describe('routing telemetry truth', () => {
 it('shows public coding task and complexity without inventing them', () => {
  const facts=routeFacts({decision:{task_type:'DEBUG',complexity:'simple'}});
  expect(facts).toContainEqual({label:'Coding task',value:'DEBUG'});
  expect(facts).toContainEqual({label:'Complexity',value:'simple'});
 });
 it('renders legacy routing without fabricating a decision', () => {
  expect(routeFacts({model:'legacy',capability:'text',reason:'old route'})).toEqual([]);
  expect(routingModel({model:'legacy'})).toBe('legacy');
 });
 it('exposes only public allowlisted fields and measured nonnegative finite times', () => {
  const decision={intent:'general_question',inference_time:-1,model_load_time:Infinity,chain_of_thought:'private',reasoning:'private'};
  expect(routeFacts({decision})).toEqual([{label:'Intent',value:'general_question'}]);
 });
 it('omits unknown fields and never invents timing or fallback', () => {
  expect(routeFacts({ decision: { selected_model: null, inference_time: null, fallback: null } })).toEqual([]);
  expect(routeFacts({ decision: { routing_time: 'fast', errors: [] } })).toEqual([]);
 });
 it('retains measured zero and false state and real reasons', () => {
  const facts=routeFacts({ decision: { routing_time: 0, switch_required: false, route_reason: 'Only admissible candidate', candidate_rejection_reasons: { vision: ['unsupported_modality'] } } });
  expect(facts).toContainEqual({label:'Route time',value:'0.000 s'});
  expect(facts).toContainEqual({label:'Switch required',value:'No'});
  expect(facts.some(f=>f.value.includes('unsupported_modality'))).toBe(true);
  expect(routingModel({model:'old',decision:{selected_model:'actual'}})).toBe('actual');
 });
 it('distinguishes permission from actual evidence use and retrieval', () => {
  const facts=routeFacts({decision:{knowledge_scope:{connected:true,mode:'all',permitted_document_count:16},evidence_required:false,evidence_used:false,retrieval:{status:'not_required',document_count:0,passage_count:0,candidate_count:0}}});
  expect(facts).toContainEqual({label:'Knowledge permission',value:'Connected · all · 16 permitted documents'});
  expect(facts).toContainEqual({label:'Evidence used',value:'Not used'});
  expect(facts).toContainEqual({label:'Retrieved',value:'0 documents · 0 passages'});
  expect(routeFacts({decision:{knowledge_scope:{connected:true,mode:'all'}}}).some(f=>f.label==='Evidence used')).toBe(false);
 });
 it('shows canonical measured millisecond timings once, with legacy compatibility', () => {
  const facts=routeFacts({decision:{timings:{classification_ms:0,routing_ms:100,retrieval_ms:250,prefill_ms:null,generation_ms:-1,total_ms:Infinity},routing_time:99,inference_time:1}});
  expect(facts.filter(f=>f.label==='Route time')).toEqual([{label:'Route time',value:'0.100 s'}]);
  expect(facts).toContainEqual({label:'Retrieval time',value:'0.250 s'});
  expect(facts).toContainEqual({label:'Inference time',value:'1.000 s'});
  expect(facts.some(f=>['Prefill time','Generation time','Total time'].includes(f.label))).toBe(false);
 });
 it('uses semantic candidate states without leaking nested private data', () => {
  const facts=routeFacts({decision:{candidate_models:[{model_id:'text',status:'selected',chain_of_thought:'private'},{model_id:'vision',admissible:false,admission:{reasons:['unsupported_modality'],private:'secret'}}],tools:[{name:'calculator',status:'completed',reason:'Registered arithmetic tool',private:'secret'}],resource_admission:{status:'conditional',observed:{available_memory_mib:0,gpu_free_mib:null},reasoning:'private'}}});
  expect(facts).toContainEqual({label:'Candidates',value:'✓ text\n× vision — unsupported_modality'});
  expect(facts).toContainEqual({label:'Tools',value:'calculator · completed — Registered arithmetic tool'});
  expect(facts).toContainEqual({label:'Resource admission',value:'conditional\nAvailable RAM: 0.0 MiB'});
  expect(JSON.stringify(facts)).not.toMatch(/private|secret/);
 });
 it('renders actual failure layer and boolean validation checks without raw logs', () => {
  const facts=routeFacts({decision:{failure_layer:'RESOURCE_FAILURE',validation:{status:'failed',checks:{syntax_valid:true,artifact_verified:false,semantic_support:null,private:'secret'}},errors:[{code:'resource_refused',message:'Insufficient GPU headroom',stack:'private'}]}});
  expect(facts).toContainEqual({label:'Failure layer',value:'RESOURCE_FAILURE'});
  expect(facts).toContainEqual({label:'Validation checks',value:'✓ syntax_valid\n× artifact_verified'});
  expect(JSON.stringify(facts)).not.toMatch(/private|secret|semantic_support/);
 });
});
