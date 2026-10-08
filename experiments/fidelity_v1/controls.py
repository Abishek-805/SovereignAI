"""Positive and negative oracle controls, executed only in existing Docker."""
import json,shlex
from experiments.fidelity_v1.tasks import ROOT,OUT,cases,freeze
from experiments.fidelity_v1.runners import property_results
from experiments.kernel_docker import DockerCommands
SCRIPT='''import os,shutil,subprocess,sys
from pathlib import Path
root=Path('/output/project');shutil.copytree('/input',root,ignore=lambda source,names:{'program.py'} if Path(source)==Path('/input') else set())
os.chdir(root)
result=subprocess.run([sys.executable,'-c',"import unittest,sys; s=unittest.TestLoader().discover('.'); print('ORACLE_COUNT='+str(s.countTestCases())); r=unittest.TextTestRunner(verbosity=2).run(s); sys.exit(0 if r.wasSuccessful() and s.countTestCases()>0 else 1)"],capture_output=True,text=True)
print(result.stdout,end='');print(result.stderr,end='',file=sys.stderr);sys.exit(result.returncode)
'''
def check(files,sandbox):
 r=sandbox.execute(SCRIPT,timeout=120,input_files={n:t.encode() for n,t in files.items()})
 return {'exit_code':r.exit_code,'container_executed':r.executed,'stdout':r.stdout,'stderr':r.stderr,'properties':property_results({'stderr':r.stderr})}
def main():
 directory=OUT/'reports/oracle-controls';directory.mkdir(parents=True,exist_ok=True)
 rows=[];sandbox=DockerCommands(ROOT,directory/'sandbox').sandbox
 for task in cases():
  path=directory/(task['task_id']+'.json')
  if path.exists():row=json.loads(path.read_text())
  else:
   bad=check(task['files'],sandbox);good=check({**task['files'],**task['positive_changes']},sandbox)
   row={'task_id':task['task_id'],'negative':bad,'positive':good,'control_passed':bad['container_executed'] and bad['exit_code']!=0 and good['container_executed'] and good['exit_code']==0 and bool(good['properties'])}
   path.write_text(json.dumps(row,indent=2),encoding='utf-8')
  rows.append(row);print(task['task_id'],row['control_passed'],flush=True)
  if not row['control_passed']:raise RuntimeError('Oracle adequacy failed before benchmark: '+task['task_id'])
 (directory/'summary.json').write_text(json.dumps({'tasks':len(rows),'controls':len(rows)*2,'all_passed':all(r['control_passed'] for r in rows),'sandbox_image_id':sandbox.image_id},indent=2),encoding='utf-8')
 if not (OUT/'reports/tasks.json').exists():freeze()
if __name__=='__main__':main()
