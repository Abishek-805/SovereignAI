"""Version 2 checks omitted public APIs, without changing requests or fixtures."""
API_CHECKS={
'mf01':("normalize_name", "unique_names", "self.assertEqual(core.normalize_name(' A  B '),'a b'); self.assertEqual(rules.unique_names([' A ','a']),['a'])"),
'mf02':("parse_pair", "merge_pairs", "self.assertEqual(core.parse_pair(' a = b '),('a','b')); self.assertRaises(ValueError,core.parse_pair,'a=b=c'); self.assertEqual(rules.merge_pairs(['a=1','a=2']),{'a':'2'})"),
'mf03':("distance", "closest", "self.assertEqual(core.distance((-2,1)),3); self.assertIsNone(rules.closest([]))"),
'mf04':("parse_amount", "total", "from decimal import Decimal; self.assertEqual(core.parse_amount('0.1'),Decimal('0.1')); self.assertRaises(ValueError,core.parse_amount,'NaN'); self.assertEqual(rules.total(['0.1','0.2']),Decimal('0.3'))"),
'mf05':("overlaps", "conflicts", "self.assertFalse(core.overlaps((0,2),(2,3))); self.assertEqual(rules.conflicts([(0,2),(1,3)]),[(0,1)])"),
'mf06':("clean_word", "frequencies", "self.assertEqual(core.clean_word('Hi!'),'hi'); self.assertEqual(rules.frequencies(['Hi!','hi']),{'hi':2})"),
'mf07':("valid_port", "ports", "core.valid_port(80); self.assertRaises(ValueError,core.valid_port,True); self.assertEqual(rules.ports([443,80,80]),[80,443])"),
'mf08':("parse_date", "earliest", "from datetime import date; self.assertEqual(core.parse_date('2024-02-29'),date(2024,2,29)); self.assertRaises(ValueError,core.parse_date,'2023-02-29'); self.assertIsNone(rules.earliest([]))"),
'cx01':("topological_order", "validate_order", "self.assertEqual(core.topological_order({'b':['a']}),['a','b']); self.assertRaises(ValueError,core.topological_order,{'a':['a']}); self.assertFalse(rules.validate_order({'b':['a']},['b','a']))"),
'cx02':("flatten", "chunks", "self.assertEqual(core.flatten([1,[2,None],(3,4)]),[1,2,None,(3,4)]); self.assertEqual(rules.chunks([1,2,3],2),[[1,2],[3]]); self.assertRaises(ValueError,rules.chunks,[1],True)"),
'cx03':("tokenize", "parse_options", "self.assertEqual(core.tokenize('--name \"A B\"'),['--name','A B']); self.assertEqual(rules.parse_options(['--x=2','--flag']),{'x':'2','flag':True}); self.assertRaises(ValueError,rules.parse_options,['plain'])"),
'cx04':("decode_runs", "encode_runs", "self.assertEqual(core.decode_runs([('x',2),('y',0)]),['x','x']); self.assertRaises(ValueError,core.decode_runs,[('x',-1)]); self.assertEqual(rules.encode_runs(['x','x','y']),[('x',2),('y',1)])"),
'cx05':("parse_rows", "summarize", "self.assertEqual(core.parse_rows('category,amount\\n\"a,b\",2\\n'),[{'category':'a,b','amount':'2'}]); from decimal import Decimal; self.assertEqual(rules.summarize([{'category':'x','amount':'0.1'},{'category':'x','amount':'0.2'}]),{'x':Decimal('0.3')}); self.assertRaises(ValueError,rules.summarize,[{'category':'x','amount':'NaN'}])"),
'cx06':("normalize_path", "index_paths", "self.assertEqual(core.normalize_path('./a//b'),'a/b'); self.assertRaises(ValueError,core.normalize_path,'a/../b'); self.assertEqual(rules.index_paths(['a//b','./a/b']),['a/b'])"),
'cx07':("merge_intervals", "covered_length", "self.assertEqual(core.merge_intervals([(3,5),(1,3)]),[(1,5)]); self.assertRaises(ValueError,core.merge_intervals,[(2,1)]); self.assertEqual(rules.covered_length([(1,3),(2,4)]),3)"),
'cx08':("resolve_alias", "resolve_all", "self.assertEqual(core.resolve_alias('a',{'a':'b','b':'c'}),'c'); self.assertRaises(ValueError,core.resolve_alias,'a',{'a':'a'}); self.assertEqual(rules.resolve_all(['a','x'],{'a':'b'}),['b','x'])"),
'cx09':("parse_events", "latest_by_id", "from datetime import datetime; dt=datetime.fromisoformat('2024-01-01T00:00:00+00:00'); self.assertEqual(core.parse_events([{'id':'a','timestamp':dt.isoformat()}]),[('a',dt)]); self.assertRaises(ValueError,core.parse_events,[{'id':'a','timestamp':'2024-01-01'}]); self.assertTrue(rules.latest_by_id([('a',dt)]))"),
}

def supplemental_test(task_id):
    if task_id not in API_CHECKS:return ''
    core_name,rules_name,assertions=API_CHECKS[task_id]
    return ('import unittest\nimport core, rules\nclass SupplementalPublicAPI(unittest.TestCase):\n'
            ' def test_independent_public_contract(self):\n  '+assertions+'\n'
            ' def test_symbols_remain_callable(self):\n'
            f'  self.assertTrue(callable(getattr(core,{core_name!r},None))); self.assertTrue(callable(getattr(rules,{rules_name!r},None)))\n')
