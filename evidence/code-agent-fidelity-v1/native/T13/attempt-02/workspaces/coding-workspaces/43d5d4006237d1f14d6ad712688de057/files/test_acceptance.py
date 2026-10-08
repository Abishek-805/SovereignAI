import unittest,json,subprocess,sys
from pathlib import Path
import lifecycle
class Check(unittest.TestCase):
 def test_value(self):self.assertEqual(lifecycle.value(),31)
 def test_integer(self):self.assertIsInstance(lifecycle.value(),int)
