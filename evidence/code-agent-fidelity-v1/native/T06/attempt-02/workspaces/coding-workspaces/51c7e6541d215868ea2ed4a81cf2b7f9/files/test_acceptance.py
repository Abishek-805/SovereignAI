import unittest,json,subprocess,sys
from pathlib import Path
import events,report
class Check(unittest.TestCase):
 def test_count(self):self.assertEqual(events.counts([{'kind':'b'},{'kind':'a'},{'kind':'b'}]),{'a':1,'b':2})
 def test_render(self):self.assertEqual(report.render([{'kind':'b'},{'kind':'a'},{'kind':'b'}]),'a:1\nb:2')
 def test_invalid(self):
  with self.assertRaises(ValueError):events.counts([{}])
 def test_preserved(self):self.assertEqual(events.version(),'v1')
