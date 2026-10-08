import unittest,json,subprocess,sys
from pathlib import Path
import stats
class Check(unittest.TestCase):
 def test_mean(self):self.assertEqual(stats.mean([2,4,9]),5)
 def test_single(self):self.assertEqual(stats.mean([8]),8)
 def test_empty(self):
  with self.assertRaises(ValueError):stats.mean([])
 def test_preserved(self):self.assertEqual(stats.tag(),'stable')
