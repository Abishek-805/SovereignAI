"""Two independently bounded phases. Partial evidence is never promoted to a winner."""
import json, os, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence/rag-fast-comparison/20261009'
ARMS=['CURRENT_BASELINE','E5_QDRANT_HYBRID','BGE_M3_QDRANT_HYBRID']
def save(name,v):
    (OUT/name).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
def phase(name,commands):
    started=time.monotonic();results=[]
    for arm,command in commands:
        remaining=600-(time.monotonic()-started)
        if remaining<=0:break
        print(name,arm,'remaining',round(remaining,1),flush=True)
        with (OUT/(name+'-'+arm+'.log')).open('w',encoding='utf-8') as log:
            process=subprocess.Popen(command,cwd=ROOT,env=dict(os.environ,RAG_COMPARISON_OUT=str(OUT),PYTHONIOENCODING='utf-8'),stdout=log,stderr=subprocess.STDOUT)
            try:rc=process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                # Windows venv launchers have a child; terminate the owned tree, not just its launcher.
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=log,stderr=subprocess.STDOUT)
                process.wait();rc=124
        results.append({'arm':arm,'exit_code':rc,'elapsed_phase':time.monotonic()-started})
        save(name+'-progress.json',{'status':'PARTIAL' if rc else 'RUNNING','results':results})
        if rc==124:break
    status='COMPLETE' if len(results)==3 and all(r['exit_code']==0 for r in results) else 'PARTIAL'
    save(name+'-progress.json',{'status':status,'budget_seconds':600,'elapsed':time.monotonic()-started,'results':results})
    return status
if __name__=='__main__':
    assert sys.argv[1] in {'retrieval','generation'}
    which=sys.argv[1]
    python=ROOT/('experiments/rag_v2/.venv/Scripts/python.exe' if which=='retrieval' else '.app-venv/Scripts/python.exe')
    script='experiments.rag_v2.compare' if which=='retrieval' else 'experiments.rag_v2.generate'
    phase(which,[(a,[str(python),'-m',script,a]) for a in ARMS])
