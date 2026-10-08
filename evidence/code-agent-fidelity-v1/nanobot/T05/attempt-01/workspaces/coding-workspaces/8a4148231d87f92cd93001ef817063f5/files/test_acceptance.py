import unittest,json,subprocess,sys
from pathlib import Path
from app import app
class Check(unittest.TestCase):
 def test_numeric(self):self.assertEqual(app.test_client().post('/double',json={'value':3.5}).get_json(),{'result':7.0})
 def test_negative(self):self.assertEqual(app.test_client().post('/double',json={'value':-2}).get_json(),{'result':-4})
 def test_invalid(self):
  for body in ({},{'value':True},{'value':'bad'},[]):
   r=app.test_client().post('/double',json=body);self.assertEqual(r.status_code,422);self.assertTrue(r.is_json)
 def test_malformed(self):
  r=app.test_client().post('/double',data='{broken',content_type='application/json');self.assertEqual(r.status_code,422);self.assertTrue(r.is_json)
 def test_preserved(self):self.assertEqual(app.test_client().get('/health').get_json(),{'ok':True})
