import unittest,json,subprocess,sys
from pathlib import Path
import numbers_io
class Check(unittest.TestCase):
 def test_new_symbol(self):self.assertEqual(numbers_io.load_number(),23)
 def test_old_removed(self):self.assertFalse(hasattr(numbers_io,'read_number'))
 def test_caller(self):self.assertEqual(subprocess.check_output([sys.executable,'caller.py'],text=True).strip(),'23')
