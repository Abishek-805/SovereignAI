import unittest,json,subprocess,sys
from pathlib import Path
import inventory
class Check(unittest.TestCase):
 def setUp(self):inventory.items.clear();inventory.items[42]={'quantity':2}
 def test_string_id(self):inventory.set_quantity('42',9);self.assertEqual(inventory.items,{42:{'quantity':9}})
 def test_integer_id(self):inventory.set_quantity(42,7);self.assertEqual(inventory.items[42]['quantity'],7)
 def test_invalid(self):
  for ident,quantity in ((True,2),(42,-1),(42,False),(42,1.5)):
   with self.assertRaises(ValueError):inventory.set_quantity(ident,quantity)
 def test_unknown(self):
  with self.assertRaises(KeyError):inventory.set_quantity('99',2)
  self.assertNotIn(99,inventory.items)
 def test_preserved(self):self.assertEqual(inventory.label(),'warehouse')
