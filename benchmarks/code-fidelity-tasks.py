"""Phase C independently authored contracts; never derived from heldout data.

Private test source is offline evidence and is never sent to evaluated models.
Each task is a distinct behavior contract, not paraphrases of one implementation.
"""
def tasks():
    contracts = [
      ('ledger','balance(entries)', 'Sum signed integer entries; reject a non-integer (including bool) with TypeError; empty gives 0; never mutate entries.',
       "assert f([5,-2,0])==3\nassert f([])==0\nraises(TypeError,lambda:f([True]))\nraises(TypeError,lambda:f(['2']))", '[5,-2]'),
      ('ranges','merge_ranges(intervals)', 'Merge overlapping or touching inclusive integer interval pairs; sort result; reversed pair raises ValueError; input unchanged; empty gives [].',
       "assert f([(5,8),(1,3),(3,6)])==[(1,8)]\nassert f([(1,2),(4,5)])==[(1,2),(4,5)]\nassert f([])==[]\nraises(ValueError,lambda:f([(4,1)]))", '[(1,3),(2,5)]'),
      ('paths','lookup(data, path)', 'Follow a tuple of mapping keys. Empty path returns data itself. Missing key raises KeyError, never returns an exception. A non-mapping intermediate raises TypeError.',
       "d={'a':{'b':0}}\nassert f(d,('a','b'))==0\nassert f(d,()) is d\nraises(KeyError,lambda:f(d,('missing',)))\nraises(TypeError,lambda:f({'a':3},('a','b')))", "{'a':{'b':2}}, ('a','b')"),
      ('csvrows','parse_line(text)', 'Parse one CSV record with Python csv rules, preserving quoted commas and empty fields. Multiple records raise ValueError; empty text returns [].',
       "assert f('a,\"b,c\",')==['a','b,c','']\nassert f('')==[]\nraises(ValueError,lambda:f('a\\nb'))", "'a,b'"),
      ('money','split_cents(total, count)', 'Split a nonnegative integer cent total into count shares differing by at most one; larger shares come first; count<=0 or total<0 raises ValueError; exact sum preserved.',
       "assert f(10,3)==[4,3,3]\nassert f(0,2)==[0,0]\nassert f(2,4)==[1,1,0,0]\nraises(ValueError,lambda:f(1,0))\nraises(ValueError,lambda:f(-1,3))", '10,3'),
      ('topology','order_nodes(dependencies)', 'Return a deterministic lexicographically smallest topological ordering; include nodes mentioned only as dependencies; cycles raise ValueError; input mappings unchanged.',
       "assert f({'c':['a','b'],'b':['a']})==['a','b','c']\nassert f({})==[]\nraises(ValueError,lambda:f({'a':['b'],'b':['a']}))", "{'b':['a']}"),
      ('inventory','reserve(stock, requests)', 'Atomically subtract nonnegative integer requested quantities from stock. Return a fresh mapping, never mutate stock. Unknown item raises KeyError, insufficient stock or negative quantity raises ValueError.',
       "s={'a':3,'b':1}\nassert f(s,{'a':2})=={'a':1,'b':1}\nassert s=={'a':3,'b':1}\nraises(KeyError,lambda:f(s,{'x':1}))\nraises(ValueError,lambda:f(s,{'a':4}))\nraises(ValueError,lambda:f(s,{'a':-1}))", "{'a':3},{'a':1}"),
      ('escaping','escape_html(text)', 'Escape &, <, >, double quote and single quote to &amp;, &lt;, &gt;, &quot; and &#x27; respectively; process each original character once, no double escaping generated entities.',
       "assert f('&<>\"'+chr(39))=='&amp;&lt;&gt;&quot;&#x27;'\nassert f('plain')=='plain'\nassert f('')==''", "'<b>'"),
      ('pagination','page(items, number, size)', 'Use one-based page number and positive size; invalid number/size raises ValueError. Return a fresh list slice; beyond the end returns []; preserve input.',
       "x=list(range(7))\nassert f(x,2,3)==[3,4,5]\nassert f(x,4,3)==[]\nassert x==list(range(7))\nraises(ValueError,lambda:f(x,0,3))\nraises(ValueError,lambda:f(x,1,0))", '[1,2,3],1,2'),
      ('versions','compare_versions(left, right)', 'Compare dotted nonnegative integer versions returning -1,0,1. Trailing zero components are equal; malformed or negative component raises ValueError; numeric rather than lexical ordering.',
       "assert f('1.10','1.2')==1\nassert f('1','1.0.0')==0\nassert f('2','3')==-1\nraises(ValueError,lambda:f('1..2','1'))\nraises(ValueError,lambda:f('-1','0'))", "'1.2','1.3'"),
      ('rle','decode_runs(runs)', 'Expand (value,count) pairs in order; zero contributes nothing; negative count raises ValueError; non-integer count including bool raises TypeError; do not mutate runs.',
       "assert f([('a',2),('b',0),('c',1)])==['a','a','c']\nassert f([])==[]\nraises(ValueError,lambda:f([('a',-1)]))\nraises(TypeError,lambda:f([('a',True)]))", "[('a',2)]"),
      ('dedup','unique_by(records, key)', 'Preserve first record for each hashable value of the named mapping key, including falsy values; return records in original order. Missing key raises KeyError; do not mutate records.',
       "a={'id':0,'v':1};b={'id':0,'v':2};c={'id':1}\nassert f([a,b,c],'id')==[a,c]\nraises(KeyError,lambda:f([{}],'id'))\nassert f([],'id')==[]", "[{'id':1}],'id'"),
      ('dates','days_between(start, end)', 'Parse strict YYYY-MM-DD calendar dates and return signed day difference end-start; malformed or invalid dates raise ValueError; leap years work.',
       "assert f('2024-02-28','2024-03-01')==2\nassert f('2025-01-02','2025-01-01')==-1\nraises(ValueError,lambda:f('2025-02-29','2025-03-01'))\nraises(ValueError,lambda:f('2025-1-1','2025-01-02'))", "'2024-01-01','2024-01-03'"),
      ('polynomial','evaluate(coefficients, x)', 'Evaluate polynomial coefficients ordered highest degree first using Horner evaluation; empty coefficients return 0; preserve coefficient list; support negative x and floating coefficients.',
       "assert f([2,3,4],-2)==6\nassert f([],7)==0\nassert f([0.5,1],2)==2\nx=[1,2];f(x,3);assert x==[1,2]", '[2,3],4'),
      ('histogram','count_words(text)', 'Count case-folded whitespace-separated words after stripping only leading/trailing .,!?;: punctuation. Ignore tokens becoming empty. Return a dict; retain internal apostrophes.',
       "assert f('Hello, hello! ... WORLD')=={'hello':2,'world':1}\nassert f(\"don't DON'T\")=={\"don't\":2}\nassert f('')=={}", "'Hi hi!'"),
      ('queues','weave(sequences)', 'Round-robin interleave finite iterables, skipping exhausted ones; accept generators and unequal lengths; never mutate lists; empty gives [].',
       "assert f([[1,2,3],['a'],[]])==[1,'a',2,3]\nassert f([iter([1,2]),iter([3,4])])==[1,3,2,4]\nassert f([])==[]", '[[1,2],[3]]'),
      ('statistics','median(values)', 'Return numeric median without changing input; even length averages central values; empty raises ValueError; duplicates and negatives work.',
       "x=[3,1,2];assert f(x)==2;assert x==[3,1,2]\nassert f([-3,-1])==-2\nassert f([2,2,2])==2\nraises(ValueError,lambda:f([]))", '[3,1,2]'),
      ('transitions','apply_events(state, events)', 'State is a mapping of keys to integers. Events are (key, delta). Apply to a copy in order; unknown keys start at zero; negative resulting value raises ValueError atomically; original state/events stay unchanged.',
       "s={'a':2};assert f(s,[('a',-1),('b',3)])=={'a':1,'b':3};assert s=={'a':2}\nraises(ValueError,lambda:f(s,[('a',-3)]))\nassert f(s,[])==s", "{'a':2},[('a',-1)]"),
      ('network','reachable(edges, start)', 'Return sorted nodes reachable from start including start in a directed adjacency mapping; handle cycles; missing adjacency means no outgoing edges; do not mutate edges.',
       "assert f({'a':['b'],'b':['a','c']},'a')==['a','b','c']\nassert f({},'z')==['z']\nassert f({'a':['b'],'x':['a']},'b')==['b']", "{'a':['b']},'a'"),
      ('formatting','render_table(rows)', 'Render list of string rows as pipe-separated lines with newline separators and no trailing newline. Escape backslash as double backslash, pipe as backslash-pipe, actual newline as literal backslash-n; preserve input; empty gives empty string.',
       "assert f([['a','b'],['c','d']])=='a|b\\nc|d'\nassert f([['a|b']])=='a\\\\|b'\nassert f([['a\\nb']])=='a\\\\nb'\nassert f([])==''", "[['a','b']]"),
    ]
    result=[]
    for name, signature, behavior, assertions, sample in contracts:
        symbol=signature.split('(')[0]
        args=signature.split('(',1)[1][:-1]
        files={name+'.py':f'def {signature}:\n    raise NotImplementedError\n\ndef compatibility_tag():\n    return "stable"\n',
               'service.py':f'from {name} import {symbol}\n\ndef run({args}):\n    raise NotImplementedError\n\ndef service_version():\n    return 1\n',
               'unrelated.py':'MARKER = "DO_NOT_CHANGE"\ndef unrelated():\n    return 17\n'}
        checklist=[behavior,f'Keep {symbol}, compatibility_tag, run, service_version callable with their stated signatures.',
                   f'service.run must delegate to {name}.{symbol} and return its result.',
                   'Preserve compatibility_tag() == "stable" and service_version() == 1; unrelated.py must remain byte-identical.']
        request=f'Implement the two-file contract in {name}.py and service.py. '+ ' '.join(checklist)
        tests=f'''import {name} as core
import service, inspect
f=core.{symbol}
def raises(kind, call):
    try: call()
    except kind: return
    raise AssertionError("required exception was not raised")
{assertions}
assert core.compatibility_tag()=="stable"
assert service.service_version()==1
assert list(inspect.signature(f).parameters)=={args.split(', ')!r}
assert list(inspect.signature(service.run).parameters)=={args.split(', ')!r}
assert service.run({sample})==f({sample})
calls=[]
def spy(*a,**kw): calls.append((a,kw));return "delegated"
core.{symbol}=spy
if hasattr(service,"{symbol}"): service.{symbol}=spy
assert service.run({sample})=="delegated" and len(calls)==1
'''
        result.append({'id':name,'category':'complex_contract','complexity':'complex','request':request,'requirements':checklist,
          'allowed_change_paths':[name+'.py','service.py'],'context':{'initial_files':files,'active_file':name+'.py'},
          'required_symbols':{name+'.py':[symbol,'compatibility_tag'],'service.py':['run','service_version'],'unrelated.py':['unrelated']},
          'oracle':{'kind':'trusted_tests','trusted_files':{'check.py':tests},'command':['python','check.py'],'expected_exit_code':0}})
    return result
