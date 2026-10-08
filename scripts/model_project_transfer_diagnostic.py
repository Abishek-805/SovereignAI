"""Fresh creation requests using supplied independent tests; all source is model-authored."""
import json
from pathlib import Path
from scripts.model_project_understanding_diagnostic import run_case

CASES=[
 {'id':'discount_cli','request':'Create a runnable Python discount CLI application using only main.py and pricing.py, with no external packages. pricing.py exports total(prices, rate), returning the sum discounted by rate percent, rounded to two decimal places. Empty prices returns 0. Reject negative prices and rates outside 0 through 100 with ValueError. main.py imports total and accepts a JSON array of prices and a rate as command-line arguments, prints the numeric result and exits nonzero with a useful message for invalid input. Read test_acceptance.py as existing independent acceptance evidence; preserve it and all other existing files. Create only the two requested implementation files.',
  'oracle':'''from pricing import total
assert total([10,20],25)==22.5
assert total([],50)==0
assert total([19.99],15)==16.99
for prices,rate in [([-1],10),([2],-1),([2],101)]:
 try:total(prices,rate)
 except ValueError:pass
 else:raise AssertionError('Required validation missing')
run(['[10,20]','25'],'22.5');run(['[-1]','20'],None)
''',
 'acceptance':'''import unittest,subprocess,sys
from pricing import total
class Acceptance(unittest.TestCase):
 def test_calculation(self):
  self.assertEqual(total([10,20],25),22.5)
  self.assertEqual(total([],50),0)
  self.assertEqual(total([19.99],15),16.99)
 def test_invalid(self):
  for prices,rate in [([-1],10),([2],-1),([2],101)]:
   with self.assertRaises(ValueError):total(prices,rate)
 def test_cli(self):
  r=subprocess.run([sys.executable,'main.py','[10,20]','25'],capture_output=True,text=True,timeout=5)
  self.assertEqual(r.returncode,0,r.stderr)
  self.assertEqual(float(r.stdout.strip()),22.5)
  r=subprocess.run([sys.executable,'main.py','[-1]','20'],capture_output=True,text=True,timeout=5)
  self.assertNotEqual(r.returncode,0)
  self.assertTrue(r.stderr.strip() or r.stdout.strip())
'''},
 {'id':'persistent_notes','request':'Create a runnable Python notes CLI application using only main.py and notes.py and the standard library. notes.py exports list_notes(path), returning [] for an absent file, and add_note(path, text), appending a nonblank note to a UTF-8 JSON array without losing earlier notes and returning the updated list. Blank or whitespace-only notes raise ValueError. main.py imports these functions, accepts add FILE TEXT or list FILE, prints the resulting list as JSON and exits nonzero for invalid requests or malformed stored JSON. Read test_acceptance.py as supplied independent acceptance evidence. Preserve it and all other existing files. Create only the two implementation files.',
 'oracle':'''from notes import list_notes,add_note
p=Path('notes.json')
assert list_notes(p)==[]
assert add_note(p,'first')==['first']
assert add_note(p,'café')==['first','café']
assert list_notes(p)==['first','café']
try:add_note(p,'  ')
except ValueError:pass
else:raise AssertionError('Blank note accepted')
p=run(['list','notes.json'],None,expected_code=0)
assert json.loads(p.stdout)==['first','café']
run(['add','notes.json','  '],None)
Path('bad.json').write_text('bad JSON')
run(['list','bad.json'],None)
''',
 'acceptance':'''import unittest,tempfile,json,subprocess,sys
from pathlib import Path
from notes import list_notes,add_note
class Acceptance(unittest.TestCase):
 def test_persistence(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'notes.json'
   self.assertEqual(list_notes(p),[])
   self.assertEqual(add_note(p,'first'),['first'])
   self.assertEqual(add_note(p,'café'),['first','café'])
   self.assertEqual(list_notes(p),['first','café'])
   with self.assertRaises(ValueError):add_note(p,'  ')
   r=subprocess.run([sys.executable,'main.py','list',str(p)],capture_output=True,text=True,timeout=5)
   self.assertEqual(r.returncode,0,r.stderr)
   self.assertEqual(json.loads(r.stdout),['first','café'])
   p.write_text('not JSON')
   r=subprocess.run([sys.executable,'main.py','list',str(p)],capture_output=True,text=True,timeout=5)
   self.assertNotEqual(r.returncode,0)
'''}]

if __name__=='__main__':
 out=Path('outputs/model-understanding/transfer');out.mkdir(parents=True,exist_ok=True)
 results=[]
 for case in CASES:
  if (out/(case['id']+'.json')).exists():raise RuntimeError('Do not overwrite evidence')
  results.append(run_case(case,out,'transfer'))
 (out/'summary.json').write_text(json.dumps([{'id':r['case']['id'],'status':r['status'],'latency':r.get('latency')} for r in results],indent=2),encoding='utf-8')
