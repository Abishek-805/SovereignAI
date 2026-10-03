"""Offline development authoring. Does not import production routing or model code.

Contract repetition across task modes is deliberate and explicitly disclosed.
Reference implementations are authoring-only, never generation context.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# name, signature, public behavior, reference body, independent assertions
CONTRACTS = [
 ('adjacent_deltas','values','Return each next-minus-current difference; fewer than two values returns [].','return [b-a for a,b in zip(values,values[1:])]', 'assert adjacent_deltas([4,1,7])==[-3,6]\nassert adjacent_deltas([])==[]'),
 ('partition_sign','values','Return three lists of negative, zero, positive values, preserving order.','return ([v for v in values if v<0],[v for v in values if v==0],[v for v in values if v>0])','assert partition_sign([2,-1,0,-3,4])==([-1,-3],[0],[2,4])'),
 ('last_positions','values','Map each hashable value to its last zero-based position.','return {v:i for i,v in enumerate(values)}','assert last_positions(["a","b","a"])=={"a":2,"b":1}\nassert last_positions([])=={}'),
 ('consecutive_groups','values','Return lists grouping equal adjacent items; nonadjacent equal items stay separate.','import itertools\nreturn [list(g) for _,g in itertools.groupby(values)]','assert consecutive_groups([2,2,1,2])==[[2,2],[1],[2]]'),
 ('weighted_mean','values, weights','Return weighted mean; lengths differ or total weight is zero raises ValueError.','if len(values)!=len(weights) or sum(weights)==0: raise ValueError\nreturn sum(v*w for v,w in zip(values,weights))/sum(weights)','assert weighted_mean([10,20],[1,3])==17.5\ntry:\n weighted_mean([1],[0])\nexcept ValueError: pass\nelse: raise AssertionError("zero weights")'),
 ('cartesian_pairs','left, right','Return ordered Cartesian pairs, left outermost; preserve inputs.','return [(a,b) for a in left for b in right]','assert cartesian_pairs([1,2],["x","y"])==[(1,"x"),(1,"y"),(2,"x"),(2,"y")]'),
 ('pad_to','values, size, fill','Return a copy padded on the right to size; never truncate a longer input.','return list(values)+[fill]*max(0,size-len(values))','assert pad_to([1],3,0)==[1,0,0]\nassert pad_to([1,2],1,0)==[1,2]'),
 ('drop_every','values, n','Remove each nth item counting from one; n<=0 raises ValueError.','if n<=0: raise ValueError\nreturn [v for i,v in enumerate(values,1) if i%n]','assert drop_every([1,2,3,4,5],2)==[1,3,5]'),
 ('longest_word','text','Return first longest whitespace-separated word; empty text returns None.','words=text.split()\nreturn max(words,key=len) if words else None','assert longest_word("cat bear wolf")=="bear"\nassert longest_word(" ") is None'),
 ('strip_prefix_once','text, prefix','Remove prefix exactly once if present; otherwise preserve text.','return text[len(prefix):] if text.startswith(prefix) else text','assert strip_prefix_once("ababx","ab")=="abx"\nassert strip_prefix_once("x","ab")=="x"'),
 ('snake_to_camel','text','Convert underscore-separated words to lower camel case; skip empty segments.','parts=[p for p in text.split("_") if p]\nreturn parts[0]+"".join(p[:1].upper()+p[1:] for p in parts[1:]) if parts else ""','assert snake_to_camel("account__display_name")=="accountDisplayName"\nassert snake_to_camel("_")==""'),
 ('mask_tail','text, keep','Mask all but final keep characters with *; keep<=0 masks everything.','keep=max(0,keep)\nreturn "*"*max(0,len(text)-keep)+(text[-keep:] if keep else "")','assert mask_tail("123456",2)=="****56"\nassert mask_tail("abc",0)=="***"'),
 ('initials','name','Return uppercase first characters of whitespace-separated words.','return "".join(p[0].upper() for p in name.split())','assert initials(" ada  lovelace ")=="AL"\nassert initials("")==""'),
 ('line_numbers','text','Prefix splitlines with one-based number and colon-space; return list of strings.','return [f"{i}: {line}" for i,line in enumerate(text.splitlines(),1)]','assert line_numbers("a\\nb")==["1: a","2: b"]'),
 ('character_positions','text, character','Return every zero-based position matching character exactly.','return [i for i,c in enumerate(text) if c==character]','assert character_positions("banana","a")==[1,3,5]'),
 ('escape_html','text','Escape &, <, > and double quotes in text, in that order.','return text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace(chr(34),"&quot;")','assert escape_html("<&>")=="&lt;&amp;&gt;"'),
 ('only_digits','text','Return ASCII digits from text, preserving order; exclude non-ASCII numerals.','return "".join(c for c in text if "0"<=c<="9")','assert only_digits("a1²2٣")=="12"'),
 ('common_prefix','strings','Return longest common prefix of strings; empty collection returns empty string.','if not strings: return ""\na=min(strings); b=max(strings)\ni=0\nwhile i<min(len(a),len(b)) and a[i]==b[i]: i+=1\nreturn a[:i]','assert common_prefix(["garden","garlic","garment"])=="gar"\nassert common_prefix([])==""'),
 ('reverse_words','text','Reverse whitespace-separated word order using single spaces.','return " ".join(reversed(text.split()))','assert reverse_words(" a  b c ")=="c b a"'),
 ('find_duplicate_keys','pairs','Return keys seen more than once, in first duplicate occurrence order.','seen=set(); result=[]\nfor key,_ in pairs:\n if key in seen and key not in result: result.append(key)\n seen.add(key)\nreturn result','assert find_duplicate_keys([("a",1),("b",2),("b",3),("a",4)])==["b","a"]'),
 ('merge_defaults','defaults, overrides','Return new mapping with overrides replacing defaults; preserve both inputs.','return {**defaults,**overrides}','d={"a":1}; assert merge_defaults(d,{"a":2,"b":3})=={"a":2,"b":3}; assert d=={"a":1}'),
 ('select_keys','mapping, keys','Return mapping entries requested by keys, skip missing keys, preserve requested order.','return {k:mapping[k] for k in keys if k in mapping}','assert list(select_keys({"a":1,"b":2},["b","x","a"]))==["b","a"]'),
 ('count_by_field','records, field','Count record values for field; missing field is skipped.','out={}\nfor r in records:\n if field in r: out[r[field]]=out.get(r[field],0)+1\nreturn out','assert count_by_field([{"k":"x"},{},{"k":"x"},{"k":"y"}],"k")=={"x":2,"y":1}'),
 ('sort_records','records, field','Return stable ascending list by field; do not mutate input.','return sorted(records,key=lambda r:r[field])','r=[{"k":2,"id":"a"},{"k":1,"id":"b"},{"k":2,"id":"c"}]; assert [x["id"] for x in sort_records(r,"k")]==["b","a","c"]; assert r[0]["id"]=="a"'),
 ('rename_key','mapping, old, new','Return copy renaming old to new if present; renamed value replaces existing new.','out=dict(mapping)\nif old in out: value=out.pop(old); out[new]=value\nreturn out','assert rename_key({"a":1,"b":2},"a","b")=={"b":1}'),
 ('euclidean_squared','left, right','Return squared Euclidean distance; unequal lengths raises ValueError.','if len(left)!=len(right): raise ValueError\nreturn sum((a-b)**2 for a,b in zip(left,right))','assert euclidean_squared([1,2],[4,6])==25'),
 ('ceil_div','a, b','Return mathematical ceiling of integer a/b; zero divisor raises ZeroDivisionError.','return -(-a//b)','assert ceil_div(7,3)==3\nassert ceil_div(-7,3)==-2\nassert ceil_div(7,-3)==-2'),
 ('triangular','n','Return sum of integers 1..n; negative raises ValueError.','if n<0: raise ValueError\nreturn n*(n+1)//2','assert triangular(0)==0\nassert triangular(8)==36'),
 ('digital_root','n','Return repeated decimal digit sum for nonnegative integer; negative raises ValueError.','if n<0: raise ValueError\nreturn 0 if n==0 else 1+(n-1)%9','assert digital_root(9875)==2\nassert digital_root(0)==0'),
 ('to_base','n, base','Convert nonnegative integer to base 2..16 lowercase digits; invalid raises ValueError.','if n<0 or not 2<=base<=16: raise ValueError\nif n==0: return "0"\nout=""\nwhile n: n,r=divmod(n,base); out="0123456789abcdef"[r]+out\nreturn out','assert to_base(31,16)=="1f"\nassert to_base(5,2)=="101"'),
 ('date_offset','iso_date, days','Add integer days to ISO date and return ISO string, including leap days.','from datetime import date,timedelta\nreturn (date.fromisoformat(iso_date)+timedelta(days=days)).isoformat()','assert date_offset("2024-02-28",1)=="2024-02-29"'),
 ('minutes_to_clock','minutes','Format nonnegative minutes as unbounded hours:two-digit minutes; negatives raise ValueError.','if minutes<0: raise ValueError\nh,m=divmod(minutes,60)\nreturn f"{h}:{m:02d}"','assert minutes_to_clock(1505)=="25:05"'),
 ('overlap_length','a_start, a_end, b_start, b_end','Return length of intersection of half-open intervals; reversed endpoints raise ValueError.','if a_start>a_end or b_start>b_end: raise ValueError\nreturn max(0,min(a_end,b_end)-max(a_start,b_start))','assert overlap_length(1,5,3,7)==2\nassert overlap_length(1,3,3,4)==0'),
 ('remove_indices','values, indices','Return items except positions in indices; ignore negative and out-of-range positions.','excluded=set(indices)\nreturn [v for i,v in enumerate(values) if i not in excluded]','assert remove_indices(["a","b","c"],[1,-1,8])==["a","c"]'),
 ('interleave','left, right','Alternate items starting left; append remaining tail.','out=[]\nfor i in range(max(len(left),len(right))):\n if i<len(left): out.append(left[i])\n if i<len(right): out.append(right[i])\nreturn out','assert interleave([1,2,3],["a"])==[1,"a",2,3]'),
]

def source(spec):
    name,args,_,body,_=spec
    return f'def {name}({args}):\n'+''.join('    '+line+'\n' for line in body.splitlines())

def author_case(index, category, spec):
    name,args,requirement,body,assertions=spec
    initial=f'def {name}({args}):\n    return None\n'
    files={'solution.py':initial}
    oracle={'kind':'trusted_tests','language':'python','trusted_files':{'test_contract.py':f'from solution import {name}\n{assertions}\n'},'command':['python','test_contract.py'],'expected_exit_code':0,'test_mount':'outside_editable_workspace','success_endpoint':'READY_FOR_REVIEW'}
    request=f'Implement {name} in solution.py. {requirement}'
    kind='IMPLEMENT'; workers=['code']; complexity='simple'
    if category=='explain':
        files['solution.py']=source(spec)
        request=f'Explain the current behavior of {name}, including input handling and one concrete example. Do not edit files.'
        oracle={'kind':'human_rubric','required_facts':[requirement,'Describe actual implementation behavior, not merely a proposed implementation.'],'forbidden_claims':['Files were changed.'],'semantic_review_required':True,'success_endpoint':'ANSWERED'}
        kind='EXPLAIN'; workers=['lightweight']
    elif category=='edit':
        request=f'Edit the unfinished body of {name} in solution.py; preserve its signature. {requirement}'; kind='EDIT'
    elif category=='debug':
        request=f'Fix the regression in {name}: it returns None. Use the selected solution.py. {requirement}'; kind='DEBUG'
    elif category=='refactor_multifile':
        files={'legacy.py':initial,'solution.py':f'from legacy import {name}\n'}
        request=f'Refactor {name} from legacy.py into solution.py and implement its contract. Leave a backwards-compatible import in legacy.py. {requirement}'
        oracle['trusted_files']['test_contract.py']+=f'from legacy import {name} as compatibility\nassert compatibility is {name}\n'
        kind='MULTI_FILE_CHANGE'; complexity='medium'
    elif category=='architecture':
        files['service.py']='def execute(payload):\n    return None\n'
        files['cli.py']='print("null")\n'
        request=f'Plan briefly, then implement a three-file JSON service: solution.py provides {name}; service.py execute(payload) calls it using keys {args}; cli.py reads one JSON object from stdin and prints one JSON result. {requirement}'
        # Use an actual valid payload, expected independently during offline authoring.
        samples={'euclidean_squared':{'left':[1,2],'right':[4,6]},'ceil_div':{'a':7,'b':3},'triangular':{'n':8},'digital_root':{'n':9875},'to_base':{'n':31,'base':16}}
        sample=samples[name]
        namespace={};exec(source(spec),namespace);expected=namespace[name](**sample)
        oracle['trusted_files']['test_contract.py']+=f'''import subprocess,json
result=subprocess.run(['python','cli.py'],input=json.dumps({sample!r}),text=True,capture_output=True,timeout=5)
assert result.returncode==0, result.stderr
assert json.loads(result.stdout)=={expected!r}, 'CLI must return function result'
'''
        oracle['trusted_files']['test_contract.py']+=f'''import service, subprocess, json, inspect
payload={{key:1 for key in {args.split(', ')!r}}}
called=[]
def sentinel(*a,**kw):
 called.append((a,kw)); return 831
service.{name}=sentinel
if not hasattr(service, {name!r}): raise AssertionError('service must expose imported callable')
assert service.execute(payload)==831
assert called, 'service must delegate to function'
assert 'input(' not in inspect.getsource(service)
'''
        oracle['semantic_review_required']=True
        oracle['limitation']='Function, service delegation and one actual CLI payload are executable; broader architectural quality requires review.'
        kind='MULTI_FILE_CHANGE'; complexity='complex'; workers=['reasoning','code']
    return {'id':f'v2-main-{index:03d}','contract_id':name,'category':category,'request':request,'expected_task_type':kind,'expected_suitable_workers':workers,'complexity':complexity,'modality':'text','context':{'active_file':'solution.py','workspace_available':True,'repository_scope':'project' if category in ('architecture','refactor_multifile') else 'file','initial_files':files},'allowed_change_paths':list(files),'sandbox_required':category!='explain','execution_supported':True,'oracle':oracle,'properties':{'typo':False,'followup':False,'ambiguous':False,'repair':category=='debug'}}

def freeze(filename,cases,scope):
    value={'schema_version':1,'authored_at':'2026-10-03','author':'independent V2 fixture author agent','authorship_scope':scope,'frozen':True,'cases':cases}
    raw=json.dumps(value,indent=2,ensure_ascii=False)+'\n'
    (ROOT/filename).write_text(raw,encoding='utf-8')
    canonical=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
    return {'file':filename,'case_count':len(cases),'canonical_sha256':hashlib.sha256(canonical).hexdigest(),'file_sha256':hashlib.sha256((ROOT/filename).read_bytes()).hexdigest()}

def main():
    cases=[]
    offsets={'explain':0,'edit':7,'debug':15,'implement':20,'refactor_multifile':5,'architecture':25}
    for category,count in [('explain',20),('edit',20),('debug',20),('implement',15),('refactor_multifile',15),('architecture',5)]:
        for j in range(count): cases.append(author_case(len(cases)+1,category,CONTRACTS[(offsets[category]+j)%len(CONTRACTS)]))
    for i in [21,25,41,47,64,82]:
        case=cases[i-1]; original=case['request'];case['request']=original.replace('the','teh',1);case['properties']['typo']=True
    for i in [44,54,70,84]:
        case=cases[i-1]; original=case['request'];case['history']=[{'role':'user','content':original},{'role':'assistant','content':'The selected file remains unchanged. I can apply that contract next.'}];case['request']='Continue and apply that change.';case['properties']['followup']=True;case['context'].update(follow_up=True,previous_request=original)
    # Ambiguous write request must clarify, rather than guess an incompatible interpretation.
    case=cases[38];case['request']='Edit solution.py to make its behavior better.';case['expected_task_type']='CLARIFICATION';case['expected_suitable_workers']=['lightweight','code'];case['properties']['ambiguous']=True
    case['oracle']={'kind':'human_rubric','required_facts':['Ask for the desired behavior before applying a guessed change.'],'forbidden_claims':['A change was made or validated.'],'semantic_review_required':True,'success_endpoint':'NEEDS_INPUT'}
    from vision_assets import author_vision
    cases.extend(author_vision(ROOT,96))
    entry=freeze('main.json',cases,'New development contracts authored offline before V2 runtime tuning. No old benchmark output or old heldout.json was opened. Initial schema inspection of the old authoring script exposed its embedded legacy contract definitions; these V2 contracts were newly authored and no old output informed them.')
    (ROOT/'development-freeze.json').write_text(json.dumps(entry,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(entry))

if __name__=='__main__': main()
