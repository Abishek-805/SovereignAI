"""Offline oracle sanity checks on independent references and broken baselines.

This executes only fixture-owned stdlib examples, never models or Docker.
It reports no product performance score and cannot validate generated artifacts.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from author_development import CONTRACTS, source
from author_holdout import SPECS

ROOT=Path(__file__).resolve().parent

def check(case,files):
    with tempfile.TemporaryDirectory(prefix='sovereign-v2-fixture-') as directory:
        base=Path(directory)
        for name,content in {**files,**case['oracle']['trusted_files']}.items():
            path=base/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
        env=dict(os.environ);env['PYTHONPATH']=str(base)
        command=list(case['oracle']['command']);command[0]=sys.executable
        proc=subprocess.run(command,cwd=base,env=env,capture_output=True,text=True,timeout=15)
        return proc.returncode,proc.stderr

def main():
    report={'purpose':'Offline reference-positive and broken-baseline-negative oracle sanity, not model evaluation','reference_pass':0,'broken_baseline_fail':0,'rubric_only':0,'failures':[]}
    for split,specs in [('main',CONTRACTS),('heldout',SPECS)]:
        lookup={s[0]:s for s in specs}
        cases=json.loads((ROOT/(split+'.json')).read_text(encoding='utf-8'))['cases']
        for case in cases:
            if case['oracle']['kind']!='trusted_tests':report['rubric_only']+=1;continue
            name=case['contract_id']
            if case['category']=='vision':
                files={'index.html':(ROOT/'vision'/name.removeprefix('visual-')/'reference.html').read_text(encoding='utf-8')}
            else:
                spec=lookup[name]; files={'solution.py':source(spec)}
                if case['category']=='refactor_multifile':files['legacy.py']=f'from solution import {name}\n'
                if case['category']=='architecture':
                    files['service.py']=f'from solution import {name}\ndef execute(payload):\n    return {name}(**payload)\n'
                    files['cli.py']='import json,sys\nfrom service import execute\nprint(json.dumps(execute(json.load(sys.stdin))))\n'
            code,error=check(case,files)
            if code==0:report['reference_pass']+=1
            else:report['failures'].append({'id':case['id'],'kind':'reference_rejected','stderr':error})
            code,error=check(case,case['context']['initial_files'])
            if code!=0:report['broken_baseline_fail']+=1
            else:report['failures'].append({'id':case['id'],'kind':'broken_baseline_accepted'})
    (ROOT/'oracle-authoring-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))
    return bool(report['failures'])

if __name__=='__main__':raise SystemExit(main())
