import json,hashlib
from pathlib import Path
from router.sandbox import CodeSandbox
from scripts.full_qa_inventory import http
out=Path('outputs/interaction-repair');j=json.loads((out/'calculator-history.json').read_text(encoding='utf-8'))
draft=j['final']['result']['result'];files={c['path']:c['after'].encode() for c in draft['changes'] if c['action'] in {'create','edit'}}
assert set(files)=={'calculator.py'},files.keys()
script='''import shutil,sys,subprocess
from pathlib import Path
root=Path('/output/project');shutil.copytree('/input',root,ignore=lambda s,n:{'program.py'})
sys.path.insert(0,str(root))
from calculator import add,subtract,multiply,divide
assert add(2,3)==5
assert subtract(2,3)==-1
assert multiply(-2,3)==-6
assert divide(7,2)==3.5
for choice,expected in [('1','5.0'),('2','-1.0'),('3','6.0'),('4','0.6666666666666666')]:
 result=subprocess.run([sys.executable,str(root/'calculator.py')],input=choice+'\\n2\\n3\\n',text=True,capture_output=True,timeout=3)
 assert result.returncode==0,(result.stdout,result.stderr)
 assert expected in result.stdout,result.stdout
 print(choice,result.stdout.splitlines()[-1])
print('INDEPENDENT_ORACLE_PASS')
'''
r=CodeSandbox('docker','sha256:6f6ac11cda347a185454338dee35d77003e066579a3261b52b7c6ff1048c8573').execute(script,input_files=files)
preserved={name:hashlib.sha256(http('/coding/workspaces/'+j['workspace_id']+'/files/'+name)['body']['content'].encode()).hexdigest()==digest for name,digest in j['original_hashes'].items()}
result={'status':'PASS' if r.exit_code==0 and all(preserved.values()) else 'FAIL','sandbox_executed':r.executed,'exit_code':r.exit_code,'stdout':r.stdout,'stderr':r.stderr,'preserved_java':preserved,'candidate_sha256':hashlib.sha256(files['calculator.py']).hexdigest(),'publication':'staged QA fixture; user Summa unchanged'}
(out/'calculator-independent.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(result)
