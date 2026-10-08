import unittest,json,subprocess,sys
from pathlib import Path
import names
class Check(unittest.TestCase):
 def test_new_symbol(self):self.assertEqual(names.welcome('Ada'),'Hello Ada')
 def test_old_symbol_removed(self):self.assertFalse(hasattr(names,'greet'))
 def test_other_input(self):self.assertEqual(names.welcome('Lin'),'Hello Lin')
