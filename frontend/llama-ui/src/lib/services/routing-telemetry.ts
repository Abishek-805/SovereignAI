/** Public request-owned facts only. Unknown values are never inferred from UI state. */
export type RoutingDecision = Partial<Record<'request_id'|'intent'|'capability'|'modality'|'candidate_models'|'candidate_rejection_reasons'|'selected_model'|'runtime_alias'|'route_reason'|'required_context'|'available_context'|'resource_admission'|'current_residency'|'switch_required'|'classifier_time'|'routing_time'|'model_load_time'|'inference_time'|'validation_time'|'model_request_time'|'lease_time'|'total_time'|'fallback'|'errors'|'evidence_required'|'evidence_used'|'knowledge_scope'|'retrieval'|'tools'|'tool_candidates'|'model_candidates'|'failure_layer'|'validation'|'timings', unknown>>;
export type RoutingTelemetry = { capability?: string | null; model?: string | null; reason?: string | null; decision?: RoutingDecision | null };
export type RouteFact = { label:string; value:string };
const record=(value:unknown):Record<string,unknown>|null=>value!==null&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,unknown>:null;
const text=(value:unknown):string=>typeof value==='string'?value:'';
const finite=(value:unknown):value is number=>typeof value==='number'&&Number.isFinite(value)&&value>=0;
const count=(value:unknown):value is number=>finite(value)&&Number.isInteger(value);
const strings=(value:unknown):string[]=>Array.isArray(value)?value.filter((item):item is string=>typeof item==='string'&&!!item):[];
const boolean=(value:unknown):string=>typeof value==='boolean'?(value?'Yes':'No'):'';
function candidates(value:unknown):string {
 if(!Array.isArray(value))return '';
 return value.map(item=>{if(typeof item==='string')return '○ '+item;const candidate=record(item);if(!candidate)return '';const name=text(candidate.display_name)||text(candidate.model_id)||text(candidate.name);if(!name)return '';const state=candidate.status==='selected'?'✓':candidate.admissible===false||candidate.status==='rejected'?'×':'○';const admission=record(candidate.admission);const reason=text(candidate.reason)||strings(admission?.reasons).join('; ');return `${state} ${name}${reason?' — '+reason:''}`;}).filter(Boolean).join('\n');
}
function resource(value:unknown):string {
 const admission=record(value);if(!admission)return '';
 const rows:string[]=[];if(text(admission.status))rows.push(text(admission.status));else if(typeof admission.admitted==='boolean')rows.push(admission.admitted?'Admitted':'Refused');
 rows.push(...strings(admission.reasons),...strings(admission.conditions));const observed=record(admission.observed);
 for(const [key,label] of [['available_memory_mib','Available RAM'],['gpu_free_mib','Available GPU memory']] as const)if(finite(observed?.[key]))rows.push(`${label}: ${observed[key].toFixed(1)} MiB`);
 return rows.join('\n');
}
export function routeFacts(routing?: RoutingTelemetry | null):RouteFact[] {
 const decision=record(routing?.decision);if(!decision)return [];
 const facts:RouteFact[]=[];const add=(label:string,value:string)=>{if(value)facts.push({label,value});};
 for(const [key,label] of [['request_id','Request'],['intent','Intent'],['workflow','Workflow'],['worker_role','Worker role'],['current_stage','Task stage'],['completion_status','Completion'],['selected_tool','Selected tool'],['capability','Capability'],['modality','Modality']] as const)add(label,text(decision[key]));
 add('Worker already warm',boolean(decision.is_warm));
 add('Evidence required',boolean(decision.evidence_required));add('Evidence used',typeof decision.evidence_used==='boolean'?(decision.evidence_used?'Used':'Not used'):'');
 const scope=record(decision.knowledge_scope);if(scope){const rows:string[]=[];if(typeof scope.connected==='boolean')rows.push(scope.connected?'Connected':'Off');if(text(scope.mode))rows.push(text(scope.mode));if(count(scope.permitted_document_count))rows.push(`${scope.permitted_document_count} permitted documents`);add('Knowledge permission',rows.join(' · '));}
 const retrieval=record(decision.retrieval);if(retrieval){add('Retrieval',text(retrieval.status));const rows:string[]=[];if(count(retrieval.document_count))rows.push(`${retrieval.document_count} documents`);if(count(retrieval.passage_count))rows.push(`${retrieval.passage_count} passages`);add('Retrieved',rows.join(' · '));if(count(retrieval.candidate_count))add('Retrieval candidates',String(retrieval.candidate_count));}
 add('Candidates',candidates(decision.model_candidates??decision.candidate_models));
 const rejected=record(decision.candidate_rejection_reasons);if(rejected)add('Candidate rejection reasons',Object.entries(rejected).flatMap(([name,value])=>strings(value).map(reason=>`× ${name} — ${reason}`)).join('\n'));
 const tools=decision.tools??decision.tool_candidates;if(Array.isArray(tools))add('Tools',tools.map(item=>{const tool=record(item);if(!tool||!text(tool.name))return '';return `${text(tool.name)}${text(tool.status)?' · '+text(tool.status):''}${text(tool.reason)?' — '+text(tool.reason):''}`;}).filter(Boolean).join('\n'));
 add('Selected model',text(decision.selected_model));add('Runtime alias',text(decision.runtime_alias));add('Reason',text(decision.route_reason));
 for(const [key,label] of [['required_context','Required context'],['available_context','Available context']] as const)if(count(decision[key]))add(label,`${decision[key]} tokens`);
 add('Resource admission',resource(decision.resource_admission));add('Current residency',text(decision.current_residency));add('Switch required',boolean(decision.switch_required));
 const timings=record(decision.timings);const measured:[string,string,string][]=[['classification_ms','classifier_time','Classifier time'],['routing_ms','routing_time','Route time'],['retrieval_ms','','Retrieval time'],['load_ms','model_load_time','Model load time'],['switch_ms','','Switch time'],['prefill_ms','','Prefill time'],['generation_ms','','Generation time'],['validation_ms','validation_time','Validation time'],['total_ms','total_time','Total time']];
 for(const [milliseconds,seconds,label] of measured){if(finite(timings?.[milliseconds]))add(label,`${(timings[milliseconds]/1000).toFixed(3)} s`);else if(seconds&&finite(decision[seconds]))add(label,`${decision[seconds].toFixed(3)} s`);}
 for(const [key,label] of [['inference_time','Inference time'],['model_request_time','Model request time'],['lease_time','Lease time']] as const)if(finite(decision[key]))add(label,`${decision[key].toFixed(3)} s`);
 const fallback=record(decision.fallback);if(fallback)add('Fallback',[text(fallback.model)||text(fallback.selected_model),text(fallback.reason)].filter(Boolean).join(' — '));else add('Fallback',text(decision.fallback));
 add('Failure layer',text(decision.failure_layer));
 const validation=record(decision.validation);if(validation){add('Validation',text(validation.status));const checks=record(validation.checks);if(checks)add('Validation checks',Object.entries(checks).flatMap(([name,value])=>typeof value==='boolean'?[`${value?'✓':'×'} ${name}`]:[]).join('\n'));}
 if(Array.isArray(decision.errors))add('Errors',decision.errors.map(item=>{if(typeof item==='string')return item;const error=record(item);return error?[text(error.code),text(error.message)].filter(Boolean).join(' — '):'';}).filter(Boolean).join('\n'));
 return facts;
}
export function routingModel(routing?: RoutingTelemetry | null):string|null {const value=routing?.decision?.selected_model??routing?.model;return typeof value==='string'&&value?value:null;}
