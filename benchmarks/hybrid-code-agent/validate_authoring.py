"""Execute author-owned stdlib references and broken baselines; no product score."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from author_development import build,ROOT


def check(case,files):
    with tempfile.TemporaryDirectory(prefix='hybrid-oracle-author-') as folder:
        base=Path(folder)
        for name,content in {**files,**case['oracle']['trusted_files']}.items():
            path=base/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
        command=list(case['oracle']['command']);command[0]=sys.executable
        env=dict(os.environ);env['PYTHONPATH']=str(base)
        result=subprocess.run(command,cwd=base,env=env,capture_output=True,text=True,timeout=15)
        return result.returncode,result.stderr


def main():
    cases,references=build()
    frozen=json.loads((ROOT/'main.json').read_text(encoding='utf-8'))['cases']
    if cases!=frozen:raise ValueError('Authoring does not reproduce frozen cases')
    report={'purpose':'Offline oracle sanity only; not model evaluation','case_count':len(cases),'contract_clusters':len({c['contract_id'] for c in cases}),'reference_pass':0,'broken_baseline_fail':0,'rubric_only':0,'failures':[]}
    for case in cases:
        if case['oracle']['kind']!='trusted_tests':report['rubric_only']+=1;continue
        code,error=check(case,references[case['id']])
        if code==0:report['reference_pass']+=1
        else:report['failures'].append({'id':case['id'],'kind':'reference_rejected','stderr':error})
        code,error=check(case,case['context']['initial_files'])
        if code!=0:report['broken_baseline_fail']+=1
        else:report['failures'].append({'id':case['id'],'kind':'broken_baseline_accepted'})
    (ROOT/'oracle-authoring-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report));return bool(report['failures'])


if __name__=='__main__':raise SystemExit(main())
