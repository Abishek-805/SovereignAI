import type {CodingTask} from './coding-workspace.service';
/** Operation names are not the review contract: persisted changes are. */
export function stagedTaskFromResponse(response:any):CodingTask|undefined {
 const results=[response?.result,...(response?.result?.operations||[]).map((operation:any)=>operation.result)];
 return results.reverse().find(result=>result?.state==='completed'&&typeof result.task_id==='string'&&Array.isArray(result.changes)&&result.changes.length);
}
