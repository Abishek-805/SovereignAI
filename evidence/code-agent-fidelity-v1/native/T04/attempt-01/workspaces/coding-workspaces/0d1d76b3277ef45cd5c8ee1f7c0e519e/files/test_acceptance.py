import unittest,json,subprocess,sys
from pathlib import Path
import math_ops
class Check(unittest.TestCase):
 def test_low(self):self.assertEqual(math_ops.clamp(-7,0,8),0)
 def test_high(self):self.assertEqual(math_ops.clamp(12,0,8),8)
 def test_inside(self):self.assertEqual(math_ops.clamp(3,0,8),3)
 def test_invalid(self):
  with self.assertRaises(ValueError):math_ops.clamp(1,5,2)
 def test_preserved(self):self.assertEqual(math_ops.multiply(6,7),42)
