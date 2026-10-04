"""25 separately authored development tasks. Oracles are never worker context.

These complete the 15 pre-existing cases; no held-out data is used.
"""
def cases():
    tasks = []
    run_specs = [
        ('main.py', 'python main.py', "print('inventory ready')\n", 'inventory ready\n'),
        ('bin/launch.py', 'python bin/launch.py', "print('nested ready')\n", 'nested ready\n'),
        ('entry.py', 'python entry.py --count 3', "import argparse\np=argparse.ArgumentParser(); p.add_argument('--count',type=int); a=p.parse_args(); print(sum(range(a.count)))\n", '3\n'),
        ('tool.py', 'python tool.py', "from pathlib import Path\nprint(Path('data.txt').read_text().strip().upper())\n", 'HELLO\n'),
        ('pkg/__main__.py', 'python -m pkg', "print('module ready')\n", 'module ready\n'),
        ('report.py', 'python report.py red blue', "import sys\nprint('|'.join(sys.argv[1:]))\n", 'red|blue\n'),
        ('app/runner.py', 'python -m app.runner', "from .value import VALUE\nprint(VALUE)\n", '17\n'),
        ('cli.py', 'python cli.py', "import json\nfrom pathlib import Path\nprint(sum(json.loads(Path('settings.json').read_text())['items']))\n", '10\n'),
    ]
    for index, (entry, command, code, stdout) in enumerate(run_specs, 1):
        files = {entry:code, 'README.md':f'Run from project root with `{command}`. Expected stdout: {stdout!r}.\n',
                 'data.txt':'hello\n', 'settings.json':'{"items":[2,3,5]}',
                 'unused.py':"raise RuntimeError('This is not the entry point')\n"}
        if entry.startswith('pkg/'):
            files['pkg/__init__.py']=''
        if entry.startswith('app/'):
            files.update({'app/__init__.py':'','app/value.py':'VALUE=17\n'})
        tasks.append({'id':f'rp{index:02}', 'category':'run_project',
            'request':'Inspect this project and run its documented entry point in Docker. Preserve every file and report the actual output. Do not run unused.py.',
            'requirements':['read README.md','execute documented command', 'preserve all files','actual successful exit and exact stdout'],
            'starting_files':files, 'expected_command':command, 'expected_stdout':stdout,
            'private_test':"import unittest\nclass Contract(unittest.TestCase):\n def test_control(self): self.assertTrue(True)\n"})
    specs = [
        ('mf01','multifile','normalize_name(text) in core.py: strip edges, collapse internal whitespace, lowercase. rules.py exports unique_names(values), preserving first-occurrence order after normalization. app.py exports process(values) delegating to unique_names.',
         "self.assertEqual(process([' A  B ','a b','C']),['a b','c']); self.assertEqual(process([]),[])"),
        ('mf02','multifile','parse_pair(text) in core.py splits exactly one = into stripped nonempty key and value; otherwise raises ValueError. rules.py exports merge_pairs(lines) with last value winning. app.py process(lines) delegates to merge_pairs.',
         "self.assertEqual(process(['a=1','b=2','a=3']),{'a':'3','b':'2'}); self.assertRaises(ValueError,process,['a=']); self.assertRaises(ValueError,process,['a=b=c'])"),
        ('mf03','multifile','distance(point) in core.py returns Manhattan distance for an x,y pair. rules.py closest(points) returns the first point with minimum distance, or None if empty. app.py process(points) delegates to closest.',
         "self.assertEqual(process([(2,2),(-1,0),(0,1)]),(-1,0)); self.assertIsNone(process([]))"),
        ('mf04','multifile','parse_amount(text) in core.py returns decimal.Decimal, rejecting negative and nonfinite amounts with ValueError. rules.py total(values) sums parsed strings with Decimal. app.py process(values) returns total as a fixed-point string.',
         "self.assertEqual(process(['0.1','0.2']),'0.3'); self.assertEqual(process([]),'0'); self.assertRaises(ValueError,process,['NaN']); self.assertRaises(ValueError,process,['-1'])"),
        ('mf05','multifile','overlaps(a,b) in core.py compares two half-open numeric intervals; touching endpoints do not overlap. rules.py conflicts(intervals) returns index pairs i<j that overlap in lexicographic order. app.py process delegates to conflicts.',
         "self.assertEqual(process([(0,2),(2,3),(1,4)]),[(0,2),(1,2)]); self.assertEqual(process([]),[])"),
        ('mf06','multifile','clean_word(text) in core.py lowercases and strips punctuation from the two edges. rules.py frequencies(words) counts nonempty cleaned words. app.py process(words) returns sorted (word,count) pairs.',
         "self.assertEqual(process(['Hi!','hi','...','Cat']),[('cat',1),('hi',2)]); self.assertEqual(process([]),[])"),
        ('mf07','multifile','valid_port(value) in core.py accepts only int excluding bool, from 1 to 65535, else ValueError. rules.py ports(values) validates all and returns a sorted unique list. app.py process delegates to ports.',
         "self.assertEqual(process([80,443,80]),[80,443]); self.assertRaises(ValueError,process,[True]); self.assertRaises(ValueError,process,[0]); self.assertRaises(ValueError,process,[65536])"),
        ('mf08','multifile','parse_date(text) in core.py parses ISO YYYY-MM-DD to datetime.date. rules.py earliest(values) returns earliest parsed date or None. app.py process returns ISO string or None.',
         "self.assertEqual(process(['2024-02-29','2023-12-31']),'2023-12-31'); self.assertIsNone(process([])); self.assertRaises(ValueError,process,['2023-02-29'])"),
        ('cx01','complex','Implement topological_order(graph) in core.py for a dict of node to prerequisite list. Include referenced nodes missing keys; raise ValueError on cycles; lexicographically smallest ready node first. rules.py validate_order(graph,order) returns bool, including uniqueness and complete node coverage. app.py process(graph) computes order, validates it, returns the order.',
         "self.assertEqual(process({'c':['a','b'],'b':['a']}),['a','b','c']); self.assertRaises(ValueError,process,{'a':['b'],'b':['a']}); self.assertEqual(process({}),[]); self.assertFalse(rules.validate_order({'b':['a']},['b','a']))"),
        ('cx02','complex','Implement flatten(value) in core.py: flatten nested lists recursively, preserving non-list values including None; do not flatten tuples. rules.py chunks(values,size) returns lists of up to size items and rejects nonpositive or bool size with ValueError. app.py process(value,size) flattens then chunks.',
         "self.assertEqual(process([1,[2,[],[None]],(3,4)],2),[[1,2],[None,(3,4)]]); self.assertEqual(process([],2),[]); self.assertRaises(ValueError,process,[1],0); self.assertRaises(ValueError,process,[1],True)"),
        ('cx03','complex','Implement tokenize(text) in core.py with shlex.split. rules.py parse_options(tokens) accepts --key=value, --key value, and bare flags --key -> True; reject duplicate keys and positional tokens with ValueError. app.py process(text) tokenizes and parses.',
         "self.assertEqual(process('--name \"A B\" --count=2 --verbose'),{'name':'A B','count':'2','verbose':True}); self.assertRaises(ValueError,process,'--a=1 --a=2'); self.assertRaises(ValueError,process,'plain'); self.assertEqual(process(''),{})"),
        ('cx04','complex','Implement decode_runs(pairs) in core.py expanding (value,count), reject negative or noninteger/bool counts with ValueError. rules.py encode_runs(values) compresses consecutive equal values to (value,count). app.py process(pairs) returns the canonical encode_runs(decode_runs(pairs)).',
         "self.assertEqual(process([('a',2),('a',1),('b',0),('c',2)]),[('a',3),('c',2)]); self.assertEqual(process([]),[]); self.assertRaises(ValueError,process,[('a',-1)]); self.assertRaises(ValueError,process,[('a',True)])"),
        ('cx05','complex','Implement parse_rows(text) in core.py using csv.DictReader, preserving quoted fields. rules.py summarize(rows) groups amounts by category using Decimal; missing category or invalid/nonfinite amount raises ValueError; negative refunds allowed. app.py process(text) returns dict sorted by category with fixed-point string totals.',
         "self.assertEqual(process('category,amount\\n\"a,b\",0.1\\n\"a,b\",0.2\\nx,-2\\n'),{'a,b':'0.3','x':'-2'}); self.assertRaises(ValueError,process,'category,amount\\nx,NaN\\n'); self.assertRaises(ValueError,process,'category,amount\\n,2\\n')"),
        ('cx06','complex','Implement normalize_path(text) in core.py for safe POSIX relative paths: reject absolute paths, backslashes, .. segments, and empty paths with ValueError; remove . segments and repeated slashes. rules.py index_paths(values) deduplicates normalized paths, sorted. app.py process delegates to index_paths.',
         "self.assertEqual(process(['a//b','./a/b','c']),['a/b','c']); self.assertRaises(ValueError,process,['a/../b']); self.assertRaises(ValueError,process,['/etc/x']); self.assertRaises(ValueError,process,[''])"),
        ('cx07','complex','Implement merge_intervals(intervals) in core.py: sort and merge overlapping or touching (start,end) ranges; reject end<start with ValueError. rules.py covered_length(intervals) returns union length using merge_intervals. app.py process returns {intervals: merged list, length: union length}.',
         "self.assertEqual(process([(5,8),(1,3),(3,6)]),{'intervals':[(1,8)],'length':7}); self.assertEqual(process([]),{'intervals':[],'length':0}); self.assertRaises(ValueError,process,[(2,1)])"),
        ('cx08','complex','Implement resolve_alias(name,aliases) in core.py following aliases until terminal; cycles raise ValueError. rules.py resolve_all(names,aliases) preserves input order and duplicates. app.py process delegates to resolve_all.',
         "self.assertEqual(process(['a','x','a'],{'a':'b','b':'c'}),['c','x','c']); self.assertRaises(ValueError,process,['a'],{'a':'b','b':'a'}); self.assertEqual(process([],{}),[])"),
        ('cx09','complex','Implement parse_events(rows) in core.py returning (id,timestamp) pairs with timezone-aware datetime.fromisoformat; naive timestamps and missing id raise ValueError. rules.py latest_by_id(events) selects latest per id, preserving first encounter on equal time. app.py process(rows) returns sorted IDs mapped to ISO timestamps.',
         "self.assertEqual(process([{'id':'a','timestamp':'2024-01-01T00:00:00+00:00'},{'id':'a','timestamp':'2024-01-02T00:00:00+00:00'}]),{'a':'2024-01-02T00:00:00+00:00'}); self.assertRaises(ValueError,process,[{'id':'a','timestamp':'2024-01-01T00:00:00'}]); self.assertEqual(process([]),{})"),
    ]
    for task_id, category, request, assertions in specs:
        tasks.append({'id':task_id,'category':category,
            'request':request+' Preserve sentinel.txt and the existing health() function. Use only Python standard library.',
            'requirements':[request,'health() returns "ok"','sentinel.txt unchanged','all three modules remain'],
            'starting_files':{'core.py':'# Implement core functions here.\n','rules.py':'import core\n',
                'app.py':'import rules\ndef health():\n    return "ok"\n\ndef process(*args):\n    raise NotImplementedError\n', 'sentinel.txt':'KEEP\n'},
            'private_test':'import unittest\nfrom pathlib import Path\nimport core, rules\nfrom app import process, health\nclass Contract(unittest.TestCase):\n def test_contract(self):\n  '+assertions+'\n def test_preservation(self):\n  self.assertEqual(health(),"ok"); self.assertEqual(Path("sentinel.txt").read_text(),"KEEP\\n")\n'})
    assert len(tasks)==25
    return tasks
