import unittest,json,subprocess,sys
from pathlib import Path
from app import app
class Check(unittest.TestCase):
 def test_wire(self):
  payload=json.loads(subprocess.check_output(['node','-e',"console.log(JSON.stringify(require('./ui.js').buildPayload('  Ada  ')))"],text=True))
  self.assertEqual(payload,{'display_name':'Ada'});self.assertEqual(app.test_client().post('/profile',json=payload).get_json(),payload)
 def test_form(self):self.assertIn('name="display_name"',Path('form.html').read_text())
 def test_invalid(self):
  r=app.test_client().post('/profile',json={'display_name':' '});self.assertEqual(r.status_code,422);self.assertTrue(r.is_json)
 def test_preserved(self):self.assertEqual(app.test_client().get('/health').get_json(),{'ok':True})
