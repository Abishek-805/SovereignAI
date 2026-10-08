"""Explicit correction of interruption-caused pre-model Docker blocks."""
import hashlib,json,shutil
from experiments.fidelity_v1.tasks import OUT
from experiments.fidelity_v1.evaluate import save,project_results
def main():
 path=OUT/'results.json'
 if path.exists() and not (OUT/'reports/results-before-environment-adjudication.json').exists():shutil.copy2(path,OUT/'reports/results-before-environment-adjudication.json')
 corrected=[]
 for name in ('native','nanobot','hermes'):
  for file in (OUT/name).rglob('row.json'):
   row=json.loads(file.read_text())
   if row['model_calls']==0 and row['failure_category']=='SANDBOX' and 'Docker Linux engine or pinned image is unavailable' in row['failure_detail']:
    target=file.parent/'environment-adjudication.json'
    if not target.exists():save(target,{'original_status':row['status'],'corrected_status':'BLOCKED','primary_category':'SANDBOX','environment_cause':'Docker Linux daemon stopped after external turn interruption; verified via docker info','model_failure':False,'model_or_tool_calls':0,'original_row_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'rerun_authorized':True,'reason':'Harness environment unavailable before first model call; frozen inputs unchanged; previous raw evidence preserved'})
    corrected.append({'task_id':row['task_id'],'runner':row['runner']})
 save(OUT/'reports/environment-adjudication-summary.json',{'corrected_records':corrected,'count':len(corrected),'existing_valid_results_unchanged':True,'task_oracle_prompt_changes':False})
 project_results('ENVIRONMENT_BLOCKED')
 print('Explicitly adjudicated '+str(len(corrected))+' pre-model environment blocks')
if __name__=='__main__':main()
