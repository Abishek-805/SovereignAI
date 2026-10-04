"""Independent supplemental-oracle positive controls; not model outcomes."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments.kernel_docker import DockerCommands
from experiments.oracle_supplements import supplemental_test

REFERENCES={
'mf01':("def normalize_name(text): return ' '.join(text.split()).lower()", "def unique_names(values): return list(dict.fromkeys(core.normalize_name(v) for v in values))", "rules.unique_names(values)","values"),
'mf02':("def parse_pair(text):\n parts=text.split('=')\n if len(parts)!=2 or not all(p.strip() for p in parts): raise ValueError('pair')\n return tuple(p.strip() for p in parts)","def merge_pairs(lines): return dict(core.parse_pair(x) for x in lines)","rules.merge_pairs(values)","values"),
'mf03':("def distance(point): return abs(point[0])+abs(point[1])", "def closest(points): return min(points,key=core.distance) if points else None", "rules.closest(values)","values"),
'mf04':("from decimal import Decimal\ndef parse_amount(text):\n try: value=Decimal(text)\n except Exception as exc: raise ValueError('amount') from exc\n if not value.is_finite(): raise ValueError('amount')\n return value", "from decimal import Decimal\ndef total(values): return sum((core.parse_amount(x) for x in values),Decimal(0))", "str(rules.total(values))","values"),
'mf05':("def overlaps(a,b): return a[0]<b[1] and b[0]<a[1]", "def conflicts(intervals): return [(i,j) for i in range(len(intervals)) for j in range(i+1,len(intervals)) if core.overlaps(intervals[i],intervals[j])]", "rules.conflicts(values)","values"),
'mf06':("def clean_word(text): return ''.join(c for c in text.lower() if c.isalnum())", "from collections import Counter\ndef frequencies(values): return dict(Counter(core.clean_word(v) for v in values if core.clean_word(v)))", "rules.frequencies(values)","values"),
'mf07':("def valid_port(value):\n if type(value) is not int or not 1<=value<=65535: raise ValueError('port')\n return value", "def ports(values):\n for x in values: core.valid_port(x)\n return sorted(set(values))", "rules.ports(values)","values"),
'mf08':("from datetime import date\ndef parse_date(text):\n try: return date.fromisoformat(text)\n except Exception as exc: raise ValueError('date') from exc", "def earliest(values): return min((core.parse_date(x) for x in values),default=None)", "rules.earliest(values)","values"),
'cx01':("def topological_order(graph):\n nodes=set(graph)|{d for deps in graph.values() for d in deps}; result=[]\n while nodes:\n  ready=sorted(n for n in nodes if all(d in result for d in graph.get(n,[])))\n  if not ready: raise ValueError('cycle')\n  result.append(ready[0]); nodes.remove(ready[0])\n return result", "def validate_order(graph,order):\n positions={n:i for i,n in enumerate(order)}\n return all(n in positions and all(d in positions and positions[d]<positions[n] for d in ds) for n,ds in graph.items())", "core.topological_order(values)","values"),
'cx02':("def flatten(value):\n if not isinstance(value,list): return [value]\n return [x for v in value for x in flatten(v)]", "def chunks(values,size):\n if type(size) is not int or size<=0: raise ValueError('size')\n return [values[i:i+size] for i in range(0,len(values),size)]", "rules.chunks(core.flatten(values),size)","values,size"),
'cx03':("import shlex\ndef tokenize(text): return shlex.split(text)", "def parse_options(tokens):\n result={}; i=0\n while i<len(tokens):\n  token=tokens[i]\n  if not token.startswith('--'): raise ValueError('positional')\n  pair=token[2:].split('=',1); key=pair[0]; value=pair[1] if len(pair)==2 else True\n  if len(pair)==1 and i+1<len(tokens) and not tokens[i+1].startswith('--'): i+=1; value=tokens[i]\n  if key in result: raise ValueError('duplicate')\n  result[key]=value; i+=1\n return result", "rules.parse_options(core.tokenize(values))","values"),
'cx04':("def decode_runs(pairs):\n result=[]\n for value,count in pairs:\n  if type(count) is not int or count<0: raise ValueError('count')\n  result.extend([value]*count)\n return result", "def encode_runs(values):\n result=[]\n for value in values:\n  if result and result[-1][0]==value: result[-1]=(value,result[-1][1]+1)\n  else: result.append((value,1))\n return result", "rules.encode_runs(core.decode_runs(values))","values"),
'cx05':("import csv,io\ndef parse_rows(text): return list(csv.DictReader(io.StringIO(text)))", "from decimal import Decimal\ndef summarize(rows):\n result={}\n for row in rows:\n  try: category=row['category']; amount=Decimal(row['amount'])\n  except Exception as exc: raise ValueError('row') from exc\n  if not category or not amount.is_finite(): raise ValueError('row')\n  result[category]=result.get(category,Decimal(0))+amount\n return result", "{k:format(v,'f') for k,v in sorted(rules.summarize(core.parse_rows(values)).items())}","values"),
'cx06':("def normalize_path(text):\n if text.startswith('/') or '\\\\' in text or '..' in text.split('/'): raise ValueError('path')\n parts=[p for p in text.split('/') if p not in ('','.')]\n if not parts: raise ValueError('path')\n return '/'.join(parts)", "def index_paths(values): return sorted(set(core.normalize_path(v) for v in values))", "rules.index_paths(values)","values"),
'cx07':("def merge_intervals(intervals):\n result=[]\n for start,end in sorted(intervals):\n  if end<start: raise ValueError('interval')\n  if result and start<=result[-1][1]: result[-1]=(result[-1][0],max(end,result[-1][1]))\n  else: result.append((start,end))\n return result", "def covered_length(intervals): return sum(b-a for a,b in core.merge_intervals(intervals))", "{'intervals':core.merge_intervals(values),'length':rules.covered_length(values)}","values"),
'cx08':("def resolve_alias(name,aliases):\n seen=set()\n while name in aliases:\n  if name in seen: raise ValueError('cycle')\n  seen.add(name); name=aliases[name]\n return name", "def resolve_all(names,aliases): return [core.resolve_alias(n,aliases) for n in names]", "rules.resolve_all(values,aliases)","values,aliases"),
'cx09':("from datetime import datetime\ndef parse_events(rows):\n result=[]\n for row in rows:\n  try: name=row['id']; timestamp=datetime.fromisoformat(row['timestamp'])\n  except Exception as exc: raise ValueError('event') from exc\n  if not name or timestamp.tzinfo is None or timestamp.utcoffset() is None: raise ValueError('event')\n  result.append((name,timestamp))\n return result", "def latest_by_id(events):\n result={}\n for name,timestamp in events:\n  if name not in result or timestamp>result[name]: result[name]=timestamp\n return result", "{k:v.isoformat() for k,v in sorted(rules.latest_by_id(core.parse_events(values)).items())}","values"),
}

def main():
    out=ROOT/'benchmarks/model-comparison/oracle-v2-positive-controls'
    out.mkdir(parents=True,exist_ok=True)
    docker=DockerCommands(ROOT,out/'docker-tasks')
    results=[]
    for name,(core,rules,expression,args) in REFERENCES.items():
        path=out/(name+'.json')
        if path.exists():results.append(json.loads(path.read_text()));continue
        files={'core.py':core+'\n','rules.py':'import core\n'+rules+'\n',
               'app.py':'import core,rules\ndef health(): return "ok"\n'+f'def process({args}): return {expression}\n',
               'test_contract.py':supplemental_test(name)}
        result=docker('python -m unittest discover -p test_contract.py',files,60)
        row={'task_id':name,'purpose':'supplemental oracle positive control, not a worker outcome',
             'reference_files':files,'validation':result}
        path.write_text(json.dumps(row,indent=2));results.append(row)
        print('oracle-control',name,result['exit_code'],flush=True)
    summary={'controls':len(results),'passed':sum(r['validation']['docker_executed'] and r['validation']['exit_code']==0 for r in results),
             'not_a_model_benchmark':True,'scope':'Supplemental APIs/delegation only; not the complete original oracle'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    if summary['passed']!=17:raise RuntimeError('Supplemental positive control failed')

if __name__=='__main__':main()
