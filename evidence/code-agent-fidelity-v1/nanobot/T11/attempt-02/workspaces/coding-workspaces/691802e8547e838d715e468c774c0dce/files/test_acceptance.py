import unittest,json,subprocess,sys
from pathlib import Path
import unique
class Check(unittest.TestCase):
 def test_order(self):self.assertEqual(unique.stable_unique([3,1,3,2]),[3,1,2])
 def test_zero(self):self.assertEqual(unique.stable_unique([0,False,2,0]),[0,2])
 def test_empty(self):self.assertEqual(unique.stable_unique(['','a','','b']),['','a','b'])
 def test_preserved(self):self.assertEqual(unique.checksum([1,2,3]),6)
