"""Fresh independent acceptance fixtures. The local model writes every application."""
import argparse
import json
from pathlib import Path
from backend.model import LocalModel
from workflows.coding_workspace import CodingWorkspace
from workflows.agent_kernel import AgentLoop
from experiments.kernel_docker import DockerCommands

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/agent-kernel-rebuild'
CASES={
 'flask':('Create a small Flask attendance application. It should store students, reject invalid attendance requests, expose an API, and include a README.',{
 'unrelated.java':'class Unrelated {}\n','web/index.html':'<h1>Unrelated page</h1>\n',
 'test_acceptance.py':'''import unittest,json,importlib
class Acceptance(unittest.TestCase):
 def test_api(self):
  from app import app
  client=app.test_client()
  created=client.post('/students',json={'id':'S1','name':'Ada'})
  self.assertIn(created.status_code,[200,201])
  self.assertIn('Ada',client.get('/students').get_data(as_text=True))
  invalid=client.post('/attendance',data='{broken',content_type='application/json')
  self.assertIn(invalid.status_code,[400,422])
  invalid=client.post('/attendance',json={'student_id':'missing','status':'invalid'})
  self.assertIn(invalid.status_code,[400,404,422])
  valid=client.post('/attendance',json={'student_id':'S1','status':'present','date':'2026-10-05'})
  self.assertIn(valid.status_code,[200,201])
  import app as module
  reloaded=importlib.reload(module).app.test_client()
  self.assertIn('Ada',reloaded.get('/students').get_data(as_text=True))
  from pathlib import Path
  self.assertTrue(Path('README.md').is_file())
  self.assertIn('python',Path('README.md').read_text().lower())
'''}),
 'node':('Create a runnable Node HTTP application in server.js, expose GET /health returning 200 and JSON {"ok":true}. Reject malformed JSON POST /echo with 400; valid JSON POST /echo echoes the body. Listen on port 3100 and include README.md. Preserve unrelated files.',{
 'keep.txt':'unrelated sentinel\n','test_acceptance.py':'''import unittest,subprocess,time,urllib.request,urllib.error,json
class Acceptance(unittest.TestCase):
 def test_http(self):
  process=subprocess.Popen(['node','server.js'])
  try:
   for i in range(50):
    try: response=urllib.request.urlopen('http://127.0.0.1:3100/health',timeout=1);break
    except OSError:time.sleep(.1)
   self.assertEqual(json.load(response),{'ok':True})
   with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:3100/echo',data=b'{broken',headers={'Content-Type':'application/json'}))
   self.assertEqual(error.exception.code,400)
   result=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:3100/echo',data=b'{"value":17}',headers={'Content-Type':'application/json'}))
   self.assertEqual(json.load(result),{'value':17})
   from pathlib import Path
   self.assertTrue(Path('README.md').is_file())
  finally:process.terminate();process.wait(timeout=5)
'''}),
 'python':('Rename answer() to value() in helpers.py and update its import and call in main.py. Keep keep.txt unchanged. The program must still print 42.',{
 'main.py':'from helpers import answer\nprint(answer())\n','helpers.py':'def answer():\n return 42\n','keep.txt':'unchanged sentinel\n',
 'test_acceptance.py':'''import unittest,subprocess,sys
class Acceptance(unittest.TestCase):
 def test_value(self):
  from helpers import value
  self.assertEqual(value(),42)
  self.assertEqual(subprocess.check_output([sys.executable,'main.py'],text=True).strip(),'42')
'''}),
 'java':('Modify Main.java and Helper.java so Main calls Helper.value() and prints 42. Rename the existing Helper.answer() function to value(), keep unrelated.txt unchanged.',{
 'Main.java':'public class Main { public static void main(String[] args){System.out.println(Helper.answer());}}\n',
 'Helper.java':'public class Helper { public static int answer(){return 42;}}\n','unrelated.txt':'preserved\n',
 'test_acceptance.py':'''import unittest,subprocess
class Acceptance(unittest.TestCase):
 def test_java(self):
  self.assertEqual(subprocess.run(['javac','Main.java','Helper.java']).returncode,0)
  self.assertEqual(subprocess.check_output(['java','Main'],text=True).strip(),'42')
  from pathlib import Path
  self.assertIn('value()',Path('Main.java').read_text())
  self.assertIn('value()',Path('Helper.java').read_text())
'''}),
 'calculator':('Create a Python calculator.py exporting calculate(left, operator, right) for +, -, *, /. Reject division by zero and unsupported operators with ValueError. Add main.py CLI taking left operator right and printing the result. Include README.md. Keep keep.txt unchanged.',{
 'keep.txt':'calculator sentinel\n','test_acceptance.py':'''import unittest,subprocess,sys
class Acceptance(unittest.TestCase):
 def test_valid(self):
  from calculator import calculate
  for op,expected in [('+',8),('-',4),('*',12),('/',3)]:self.assertEqual(calculate(6,op,2),expected)
  self.assertEqual(float(subprocess.check_output([sys.executable,'main.py','6','/','2'],text=True)),3)
  from pathlib import Path
  self.assertTrue(Path('README.md').is_file())
 def test_invalid(self):
  from calculator import calculate
  with self.assertRaises(ValueError):calculate(1,'/',0)
  with self.assertRaises(ValueError):calculate(1,'?',2)
'''}),
 'repair':('Repair the division-by-zero bug in helpers.py so answer() returns the integer 42. Preserve main.py and keep.txt unchanged. Run main.py and verify it prints 42.',{
 'main.py':'from helpers import answer\nprint(answer())\n','helpers.py':'def answer():\n return 42 / 0\n','keep.txt':'repair sentinel\n',
 'test_acceptance.py':'''import unittest,subprocess,sys
class Acceptance(unittest.TestCase):
 def test_repair(self):
  from helpers import answer
  self.assertEqual(answer(),42)
  self.assertIsInstance(answer(),int)
  self.assertEqual(subprocess.check_output([sys.executable,'main.py'],text=True).strip(),'42')
'''}),
}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('case',choices=CASES);args=parser.parse_args()
    directory=OUT/(args.case+'-'+str(__import__('time').time_ns()));directory.mkdir(parents=True)
    coding=CodingWorkspace(directory/'workspaces');wid=coding.create('Independent '+args.case)['workspace_id']
    request,fixtures=CASES[args.case]
    for name,content in fixtures.items():coding.write(wid,name,content)
    (directory/'fixture.json').write_text(json.dumps({'request':request,'files':fixtures},indent=2))
    sandbox=DockerCommands(ROOT,directory/'sandbox').sandbox
    result=AgentLoop().run(coding,wid,request,LocalModel(),sandbox,'sovereign-text',progress=lambda s:print(s,flush=True))
    (directory/'result.json').write_text(json.dumps(result,indent=2))
    assert result['state']=='completed',result.get('error')
    coding.accept(wid,result['task_id'])
    from workflows.agent_kernel import AgentSession,WorkspaceManager,ValidationEngine
    verification=ValidationEngine(WorkspaceManager(coding,wid,request),sandbox,AgentSession(request,wid,'fixed')).validate()
    (directory/'accepted-independent.json').write_text(json.dumps(verification,indent=2))
    assert verification['passed'],verification
    for name,content in fixtures.items():
        if name not in {'Main.java','Helper.java','main.py','helpers.py'} or args.case=='repair' and name=='main.py':assert coding.read(wid,name)['content']==content,name
    print('PASS',args.case,str(directory),flush=True)

if __name__=='__main__':main()
