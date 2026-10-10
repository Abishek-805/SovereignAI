"""Explicit oracle repair/recheck of unchanged saved code, not model repair."""
import json,sys
from pathlib import Path
from experiments.qlora_factory.seed import jsonl,ROOT,IMAGE
from experiments.qlora_factory.prepare import save
from router.sandbox import CodeSandbox
def main(out):
    out=out.resolve();(out/'AMENDMENTS.md').write_text('''Oracle-only repair: original rot13 Docker oracle omitted the trusted /output/project import path; original CSV oracle embedded a literal newline in JavaScript source. Both original failures retained as HARNESS defects, never model-failure evidence. Rerun exact saved model code with corrected equivalent behavioral assertions, no model call/source changes. Accept only actual independent Docker PASS. Generic QA lexical screens remain quarantine; separate independent semantic/runtime review can qualify a subset without changing teacher responses.
''')
    positive=[json.loads(x) for x in (out/'positive-trajectories.jsonl').read_text(encoding='utf-8').splitlines()]
    checks=[];sandbox=CodeSandbox('docker',IMAGE,out/'oracle-recheck-sandbox')
    for name,script in [('rot13',"import sys;sys.path.insert(0,'/output/project')\nimport main\nassert main.rot13('Hello, 123!')=='Uryyb, 123!'\nassert main.rot13(main.rot13('AbZ'))=='AbZ'\nassert main.rot13('')==''\n"),('csv',"import subprocess,json\ncases=[('a,b','\\\"a,b\\\"'),('a\\\"b','\\\"a\\\"\\\"b\\\"'),('plain','plain'),('',''),('a\\n','\\\"a\\n\\\"')]\njs=\"const {escapeField}=require('./main.js');const assert=require('assert');\"+''.join('assert.equal(escapeField('+json.dumps(a)+'),'+json.dumps(b)+');' for a,b in cases)\nsubprocess.run(['node','-e',js],check=True)\n")]:
        cell=out/'raw-trajectories'/name;record=json.loads((cell/'call-001.json').read_text(encoding='utf-8'));message=record['response']['choices'][0]['message'];code=json.loads(message['content'])['code'];filename='main.py' if name=='rot13' else 'main.js'
        runner="import shutil,os\nshutil.copytree('/input','/output/project',ignore=lambda p,n:{'program.py'} if p=='/input' else set());os.chdir('/output/project')\n"+script+"\nprint('INDEPENDENT_PASS')\n"
        (cell/'oracle-recheck.py').write_text(runner);result=sandbox.execute(runner,input_files={filename:code.encode()});passed=result.executed and result.exit_code==0
        save(cell/'oracle-recheck.json',{'executed':result.executed,'exit_code':result.exit_code,'stdout':result.stdout,'stderr':result.stderr,'candidate_unchanged':True,'passed':passed});checks.append({'id':name,'passed':passed})
        if passed:positive.append({'id':name+'-oracle-recheck','category':'coding','difficulty':'MEDIUM','family':name,'messages':[*record['request']['messages'],message],'source':{'kind':'self_generated','teacher':'Qwen/Qwen3.5-4B','not_manually_repaired':True},'quality':{'verified':True,'oracle':{'type':'corrected independent behavioral Docker oracle, raw failures preserved','passed':True}},'language':'python' if name=='rot13' else 'javascript'})
    # Two stable Python facts plus DNS definition, independently inspected; no answer edit.
    for name in ('py-bool','dns','iterator'):
        cell=out/'raw-trajectories'/name;r=json.loads((cell/'call-001.json').read_text(encoding='utf-8'));message=r['response']['choices'][0]['message']
        positive.append({'id':name+'-reviewed','category':'general_qa','difficulty':'EASY','family':name,'messages':[*r['request']['messages'],message],'source':{'kind':'self_generated','teacher':'Qwen/Qwen3.5-4B'},'quality':{'verified':True,'oracle':{'type':'independent Codex semantic review against Python truth/iteration semantics or DNS name-to-address definition; no text changes','passed':True,'limitations':'small factual coverage, not universal entailment'}}})
    save(out/'independent-review.json',{'accepted_general':['py-bool','dns','iterator'],'still_quarantined':['encoding','http','sqlnull'],'reason':'Avoid broad unsupported generalizations. Do not equate keyword screens with verification.','coding_rechecks':checks})
    jsonl(out/'positive-trajectories-reviewed.jsonl',positive);print('Reviewed positives',len(positive),checks)
if __name__=='__main__':main(Path(sys.argv[1]))
