"""Independent acceptance fixtures; deliberately contains no application source."""
import json
from pathlib import Path
from scripts.model_project_transfer_diagnostic import CASES

CASES_NEW=[CASES[0],
{'id':'temperature_error','request':'Create main.py and temperature.py, a Python CLI using only the standard library. temperature.py exports convert(value), returning value * 2 for nonnegative numbers and raising ValueError for negative numbers. main.py accepts one numeric positional argument, prints the converted number, and exits nonzero with an error message on invalid input. Preserve test_acceptance.py and all existing files; read it as independent acceptance evidence.',
'acceptance':'''import unittest,subprocess,sys
from temperature import convert
class Acceptance(unittest.TestCase):
 def test_normal(self): self.assertEqual(convert(5),10)
 def test_invalid(self):
  with self.assertRaises(ValueError): convert(-1)
 def test_cli(self):
  r=subprocess.run([sys.executable,'main.py','5'],capture_output=True,text=True,timeout=5)
  self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(float(r.stdout),10)
  r=subprocess.run([sys.executable,'main.py','-1'],capture_output=True,text=True,timeout=5)
  self.assertNotEqual(r.returncode,0);self.assertTrue(r.stderr.strip() or r.stdout.strip())
'''},
{'id':'flask_error','request':'Create app.py, a Flask API exporting app. POST /double accepts a JSON object with a numeric value field, returns HTTP 200 and JSON result equal to twice value. Malformed JSON, missing value, or nonnumeric value returns HTTP 400 with a JSON error. Preserve test_acceptance.py and all existing files; read it as independent acceptance evidence.',
'acceptance':'''import unittest
from app import app
class Acceptance(unittest.TestCase):
 def test_normal(self):
  r=app.test_client().post('/double',json={'value':5});self.assertEqual(r.status_code,200);self.assertEqual(r.get_json()['result'],10)
 def test_invalid(self):
  c=app.test_client()
  for data in [{},{'value':'bad'}]:
   r=c.post('/double',json=data);self.assertEqual(r.status_code,400);self.assertIn('error',r.get_json())
  r=c.post('/double',data='{broken',content_type='application/json');self.assertEqual(r.status_code,400);self.assertIn('error',r.get_json())
'''},
{'id':'node_error','request':'Create server.js, a Node HTTP API using only built-in modules, listening on port 3000. POST /double accepts a JSON object with a numeric value field and returns HTTP 200 with JSON result equal to twice value. Malformed JSON, missing value, and nonnumeric value return HTTP 400 with a JSON error. Preserve test_acceptance.py and all existing files; read it as independent acceptance evidence.',
'acceptance':'''import unittest,subprocess,time,urllib.request,urllib.error,json
class Acceptance(unittest.TestCase):
 def test_http(self):
  p=subprocess.Popen(['node','server.js'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  try:
   def send(data):
    req=urllib.request.Request('http://127.0.0.1:3000/double',data=data.encode(),headers={'Content-Type':'application/json'},method='POST')
    try: r=urllib.request.urlopen(req,timeout=2)
    except urllib.error.HTTPError as e: r=e
    with r: return r.code,json.loads(r.read())
   for _ in range(40):
    try: status,body=send('{"value":5}');break
    except OSError: time.sleep(.1)
   else: self.fail('Server did not become ready')
   self.assertEqual(status,200);self.assertEqual(body['result'],10)
   for data in ['{broken','{}','{"value":"bad"}']:
    status,body=send(data);self.assertEqual(status,400);self.assertIn('error',body)
  finally:
   p.terminate()
   try: p.wait(timeout=2)
   except subprocess.TimeoutExpired: p.kill();p.wait()
'''},
{'id':'age_readme','request':'Create a Python CLI project with main.py, age.py and README.md, using only the standard library. age.py exports validate(value), returning the integer unchanged for ages 0 through 120 inclusive, raising ValueError outside that range. main.py accepts one integer positional argument, prints the validated age, and exits nonzero with a useful error for invalid input. README.md must explain the exact run command. Preserve test_acceptance.py and all existing files; read it as independent acceptance evidence.',
'acceptance':'''import unittest,subprocess,sys
from pathlib import Path
from age import validate
class Acceptance(unittest.TestCase):
 def test_normal(self):
  for value in [0,30,120]:self.assertEqual(validate(value),value)
 def test_invalid(self):
  for value in [-1,121]:
   with self.assertRaises(ValueError):validate(value)
 def test_entrypoint(self):
  r=subprocess.run([sys.executable,'main.py','30'],capture_output=True,text=True,timeout=5)
  self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout.strip(),'30')
  r=subprocess.run([sys.executable,'main.py','-1'],capture_output=True,text=True,timeout=5);self.assertNotEqual(r.returncode,0)
  text=Path('README.md').read_text();self.assertIn('main.py',text);self.assertIn('python',text.lower())
'''}]

if __name__=='__main__':
    dest=Path('outputs/project-error-reliability/fixtures.json')
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():raise SystemExit('Evidence fixture already exists; do not overwrite')
    dest.write_text(json.dumps(CASES_NEW,indent=2),encoding='utf-8')
