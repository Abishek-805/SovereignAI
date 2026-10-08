import unittest,json,subprocess,sys
from pathlib import Path
import errors
class Check(unittest.TestCase):
 def test_normal(self):self.assertEqual(errors.divide(15,3),5)
 def test_exception(self):
  with self.assertRaises(ValueError):errors.divide(1,0)
 def test_preserved(self):self.assertEqual(errors.identity(),'keep')
