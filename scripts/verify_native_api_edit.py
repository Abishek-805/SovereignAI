"""Independent multi-file edit acceptance through the real task API."""
import argparse,json,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/agent-kernel-rebuild'/('coder-api-'+str(time.time_ns()))
def api(path,body=None,method=None):
    request=urllib.request.Request('http://127.0.0.1:8088'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'},method=method)
    return json.load(urllib.request.urlopen(request,timeout=180))
def main():
    p=argparse.ArgumentParser();p.add_argument('--case',choices=['edit','rename'],default='edit');args=p.parse_args()
    OUT.mkdir(parents=True)
    w=api('/coding/workspaces',{'name':'Native Coder edit QA'});wid=w['workspace_id']
    fixtures={'helpers.py':'def answer():\n    return 7\n','main.py':'from helpers import answer\nprint(answer())\n','keep.txt':'preserve me\n','test_acceptance.py':'import unittest,subprocess,sys\nfrom helpers import answer\nclass Check(unittest.TestCase):\n def test_answer(self):\n  self.assertEqual(answer(),42)\n  self.assertEqual(subprocess.check_output([sys.executable,"main.py"],text=True).strip(),"42")\n'}
    if args.case=='rename':fixtures['test_acceptance.py']=fixtures['test_acceptance.py'].replace('from helpers import answer','from helpers import value').replace('answer(),42','value(),7').replace('"42"','"7"')
    for name,content in fixtures.items():api('/coding/workspaces/'+wid+'/files/'+name,{'content':content},'PUT')
    goal='Edit helpers.py so answer returns integer 42. Ensure main.py prints 42. Preserve keep.txt and test_acceptance.py. Run the tests.'
    if args.case=='rename':goal='Rename function answer to value across both helpers.py and main.py, updating its import and call. Preserve behavior and unrelated files.'
    (OUT/'fixture.json').write_text(json.dumps({'case':args.case,'goal':goal,'files':fixtures},indent=2))
    admission=api('/agent/jobs',{'goal':goal,'workspace_id':wid,'document_ids':[]})
    (OUT/'admission.json').write_text(json.dumps(admission,indent=2))
    for _ in range(900):
        result=api('/coding/jobs/'+admission['job_id'])
        if result['state']!='running':break
        time.sleep(1)
    (OUT/'final.json').write_text(json.dumps(result,indent=2))
    assert result['state']=='completed',result.get('error') or result.get('completion')
    inner=result['result'];inner=inner.get('result',inner)
    task=inner['task_id']
    accepted=api('/coding/workspaces/'+wid+'/tasks/'+task+'/accept',{})
    (OUT/'accept.json').write_text(json.dumps(accepted,indent=2))
    for name in (('keep.txt','test_acceptance.py','main.py') if args.case=='edit' else ('keep.txt','test_acceptance.py')):
        assert api('/coding/workspaces/'+wid+'/files/'+name)['content']==fixtures[name]
    print('PASS native API edit '+str(OUT),flush=True)
if __name__=='__main__':main()
