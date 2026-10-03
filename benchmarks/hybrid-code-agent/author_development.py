"""Author new development-only contracts; no model, product, or held-out access."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
# name, parameter, requirement, reference body, public sample, independent checks
SPECS=[
('running_max','values','Return the maximum seen through each position; empty returns [].','out=[]\nfor v in values: out.append(max(v,out[-1]) if out else v)\nreturn out',[3,1,5,2],'assert running_max([3,1,5,2])==[3,3,5,5]\nassert running_max([])==[]\nassert running_max([-5,-2,-7])==[-5,-2,-2]'),
('even_position_sum','values','Sum items at zero-based even positions; empty returns zero.','return sum(values[::2])',[2,8,4,9],'assert even_position_sum([2,8,4,9])==6\nassert even_position_sum([])==0\nassert even_position_sum([-1,3,-2])==-3'),
('unique_sorted','values','Return distinct integer values in ascending order without mutating input.','return sorted(set(values))',[4,2,4,1],'v=[4,2,4,1]; assert unique_sorted(v)==[1,2,4]; assert v==[4,2,4,1]\nassert unique_sorted([])==[]'),
('reverse_chunks','values','Reverse each consecutive pair, preserving an unpaired final value and returning a new list.','return [x for i in range(0,len(values),2) for x in reversed(values[i:i+2])]',[1,2,3,4,5],'assert reverse_chunks([1,2,3,4,5])==[2,1,4,3,5]\nassert reverse_chunks([])==[]\nassert reverse_chunks([7])==[7]'),
('nonzero_runs','values','Return lengths of consecutive nonzero runs separated by zeros.','out=[]; n=0\nfor v in values:\n if v: n+=1\n elif n: out.append(n); n=0\nif n: out.append(n)\nreturn out',[1,2,0,3,0,4,5,6],'assert nonzero_runs([1,2,0,3,0,4,5,6])==[2,1,3]\nassert nonzero_runs([0,0])==[]\nassert nonzero_runs([-1])==[1]'),
('first_repeat_index','values','Return zero-based index of the first repeated hashable item, or -1.','seen=set()\nfor i,v in enumerate(values):\n if v in seen: return i\n seen.add(v)\nreturn -1',['a','b','a'],'assert first_repeat_index(["a","b","a"])==2\nassert first_repeat_index([])==-1\nassert first_repeat_index([1,1,2])==1'),
('double_spaces','text','Replace every ASCII space with two spaces; preserve tabs and all other characters.','return text.replace(" ","  ")','a b\tc','assert double_spaces("a b\\tc")=="a  b\\tc"\nassert double_spaces(" ")=="  "\nassert double_spaces("")==""'),
('word_lengths','text','Return lengths of whitespace-separated words.','return [len(w) for w in text.split()]','a blue moon','assert word_lengths(" a  blue\\nmoon ")==[1,4,4]\nassert word_lengths("")==[]'),
('collapse_hyphens','text','Collapse each run of ASCII hyphens to one hyphen; preserve other characters.','import re\nreturn re.sub("-+","-",text)','a---b--c','assert collapse_hyphens("a---b--c")=="a-b-c"\nassert collapse_hyphens("---")=="-"\nassert collapse_hyphens("a__b")=="a__b"'),
('parenthesis_balance','text','Return True only if parentheses are balanced in order; ignore other characters.','n=0\nfor c in text:\n n+=(c=="(")-(c==")")\n if n<0:return False\nreturn n==0','(a(b)c)','assert parenthesis_balance("(a(b)c)") is True\nassert parenthesis_balance(")(") is False\nassert parenthesis_balance("(") is False\nassert parenthesis_balance("") is True'),
('transpose_rect','matrix','Transpose a rectangular matrix; empty matrix returns []; reject ragged rows with ValueError.','if not matrix:return []\nif any(len(r)!=len(matrix[0]) for r in matrix):raise ValueError\nreturn [list(c) for c in zip(*matrix)]',[[1,2],[3,4]],'assert transpose_rect([[1,2],[3,4]])==[[1,3],[2,4]]\nassert transpose_rect([])==[]\nassert transpose_rect([[],[]])==[]\ntry: transpose_rect([[1],[2,3]])\nexcept ValueError: pass\nelse: raise AssertionError("ragged")'),
('row_sums','matrix','Return sum of each row, including zero for empty rows.','return [sum(r) for r in matrix]',[[1,2],[],[-1,4]],'assert row_sums([[1,2],[],[-1,4]])==[3,0,3]\nassert row_sums([])==[]'),
('second_largest','values','Return second distinct largest number; fewer than two distinct values raises ValueError.','v=sorted(set(values))\nif len(v)<2:raise ValueError\nreturn v[-2]',[4,9,9,2],'assert second_largest([4,9,9,2])==4\nassert second_largest([-5,-1,-3])==-3\ntry: second_largest([2,2])\nexcept ValueError: pass\nelse: raise AssertionError("distinct")'),
('pair_totals','pairs','Return sum of each two-item pair; preserve input order.','return [a+b for a,b in pairs]',[[1,4],[2,-3]],'assert pair_totals([(1,4),(2,-3)])==[5,-1]\nassert pair_totals([])==[]'),
('invert_unique','mapping','Invert mapping keys and values; duplicate values raise ValueError.','out={}\nfor k,v in mapping.items():\n if v in out:raise ValueError\n out[v]=k\nreturn out',{'a':1,'b':2},'assert invert_unique({"a":1,"b":2})=={1:"a",2:"b"}\nassert invert_unique({})=={}\ntry: invert_unique({"a":1,"b":1})\nexcept ValueError: pass\nelse: raise AssertionError("duplicate")'),
('trim_values','mapping','Return a new dictionary stripping whitespace from string values, retaining nonstrings unchanged.','return {k:v.strip() if isinstance(v,str) else v for k,v in mapping.items()}',{'a':' x ','b':2},'d={"a":" x ","b":2}; assert trim_values(d)=={"a":"x","b":2}; assert d["a"]==" x "\nassert trim_values({})=={}'),
('binary_ones','n','Return count of 1 bits in a nonnegative integer; negative raises ValueError.','if n<0:raise ValueError\nreturn bin(n).count("1")',13,'assert binary_ones(13)==3\nassert binary_ones(0)==0\ntry: binary_ones(-1)\nexcept ValueError: pass\nelse: raise AssertionError("negative")'),
('factorial_checked','n','Return factorial of nonnegative integer including 0=1; negative raises ValueError.','if n<0:raise ValueError\nvalue=1\nfor i in range(2,n+1):value*=i\nreturn value',5,'assert factorial_checked(5)==120\nassert factorial_checked(0)==1\ntry: factorial_checked(-1)\nexcept ValueError: pass\nelse: raise AssertionError("negative")'),
('strictly_increasing','values','Return True when every adjacent pair is strictly increasing; empty and singleton are True.','return all(a<b for a,b in zip(values,values[1:]))',[1,3,8],'assert strictly_increasing([1,3,8]) is True\nassert strictly_increasing([1,1]) is False\nassert strictly_increasing([]) is True\nassert strictly_increasing([2,1]) is False'),
('middle_item','values','Return middle item of an odd-length sequence; empty or even length raises ValueError.','if not values or len(values)%2==0:raise ValueError\nreturn values[len(values)//2]',['a','b','c'],'assert middle_item(["a","b","c"])=="b"\nassert middle_item([8])==8\ntry: middle_item([])\nexcept ValueError: pass\nelse: raise AssertionError("empty")')]


def source(spec):return f'def {spec[0]}({spec[1]}):\n'+''.join('    '+line+'\n' for line in spec[3].splitlines())


def case(index,category,spec):
    name,arg,requirement,body,sample,checks=spec
    initial=f'def {name}({arg}):\n    return None\n'
    files={'solution.py':initial}
    reference={'solution.py':source(spec)}
    tests=f'from solution import {name}\n'+checks+'\n'
    request=f'Implement {name} in solution.py. {requirement}'
    task='IMPLEMENT'; complexity='simple'; workers=['code']
    if category=='explain':
        files=reference.copy(); task='EXPLAIN'; workers=['lightweight']
        request=f'Explain {name} in solution.py, including the actual edge cases and one concrete input/output example. Do not edit files.'
    elif category=='edit':
        task='EDIT'; request=f'Edit the unfinished {name} function in solution.py; preserve its public signature. {requirement}'
    elif category=='debug':
        task='DEBUG'; request=f'Fix the None-result bug in {name} in the selected solution.py. {requirement}'
    elif category=='followup':
        task='EDIT'; request=f'Continue the earlier requested edit to {name} in solution.py. The required behavior is: {requirement}'
    elif category=='context_heavy':
        task='EDIT'; request=f'Edit only solution.py to implement {name}. {requirement} Leave unrelated modules unchanged.'
        for k in range(12): files[f'noise_{k:02}.py']='# unrelated module\n'+''.join(f'CONST_{j} = {j}\n' for j in range(30))
        reference={**files,'solution.py':source(spec)}
    elif category in {'refactor_multifile','architecture'}:
        task='MULTI_FILE_CHANGE'; complexity='medium'; files={'legacy.py':initial,'solution.py':f'from legacy import {name}\n'}
        reference={'solution.py':source(spec),'legacy.py':f'from solution import {name}\n'}
        request=f'Refactor {name} into solution.py and leave a backward-compatible import in legacy.py. Implement this behavior: {requirement}'
        tests+=f'from legacy import {name} as old_api\nassert old_api is {name}\n'
        if category=='architecture':
            complexity='complex'; workers=['reasoning','code']
            files={'solution.py':initial,'service.py':'def execute(payload):\n    return None\n','cli.py':'print("null")\n'}
            reference={'solution.py':source(spec),'service.py':f'from solution import {name}\ndef execute(payload):\n    return {name}(payload[{arg!r}])\n','cli.py':'import json,sys\nfrom service import execute\nprint(json.dumps(execute(json.load(sys.stdin))))\n'}
            request=f'Plan and implement a three-file JSON command-line architecture: solution.py defines {name}; service.py execute(payload) calls it with payload key {arg}; cli.py reads JSON stdin and prints JSON output. {requirement}'
            ns={};exec(source(spec),ns); expected=ns[name](sample)
            tests=f'from solution import {name}\n'+checks+'\n'
            tests+=f'import subprocess,json,service\np=subprocess.run(["python","cli.py"],input=json.dumps({{ {arg!r}:{sample!r} }}),text=True,capture_output=True,timeout=5)\nassert p.returncode==0,p.stderr\nassert json.loads(p.stdout)=={expected!r}\n'
            tests+=f'called=[]\ndef sentinel(value):\n called.append(value); return 911\nservice.{name}=sentinel\nassert service.execute({{ {arg!r}:{sample!r} }})==911\nassert called==[{sample!r}]\n'
    oracle={'kind':'trusted_tests','trusted_files':{'test_contract.py':tests},'command':['python','test_contract.py'],'expected_exit_code':0,'test_mount':'outside_editable_workspace','success_endpoint':'READY_FOR_REVIEW'}
    if category=='explain':oracle={'kind':'human_rubric','required_facts':[requirement,f'Explain actual {name} behavior and concrete example.'],'forbidden_claims':['Files were changed.'],'semantic_review_required':True,'success_endpoint':'ANSWERED'}
    result={'id':f'hybrid-dev-{index:03d}','contract_id':name,'category':category,'request':request,'expected_task_type':task,'expected_suitable_workers':workers,'complexity':complexity,'modality':'text','context':{'active_file':'solution.py','workspace_available':True,'repository_scope':'project' if category in {'architecture','refactor_multifile','context_heavy'} else 'file','initial_files':files},'allowed_change_paths':list(reference) if category in {'architecture','refactor_multifile'} else ['solution.py'],'sandbox_required':category!='explain','execution_supported':True,'oracle':oracle,'properties':{'typo':False,'followup':category=='followup','ambiguous':False,'repair':category=='debug','context_heavy':category=='context_heavy'}}
    if category=='followup':result['history']=[{'role':'user','content':f'Edit {name} in solution.py. {requirement}'},{'role':'assistant','content':'The selected file is unchanged; the requested implementation is pending.'}]
    if index%11==0 and category!='explain':
        result['request']=request.replace('Implement','Implment').replace('selected','seleced')
        if result['request']==request:result['request']='Pls '+request
        result['properties']['typo']=True
    return result,reference


def vision(index,variant):
    from PIL import Image,ImageDraw
    labels=[('Weather board','Refresh forecast'),('Reading list','Add title'),('Meal planner','Add meal'),('Travel notes','New note'),('Budget board','Add entry')]
    title,button=labels[variant]; color=['#173f5f','#254441','#463f5d','#42362f','#283747'][variant]
    path=ROOT/'vision'/f'board-{variant}.png';path.parent.mkdir(exist_ok=True)
    img=Image.new('RGB',(640,360),color);d=ImageDraw.Draw(img);d.text((30,28),title,fill='white');d.rounded_rectangle((30,82,610,252),radius=12,fill='#eeeeee');d.text((50,110),'No items yet',fill='black');d.rectangle((30,280,220,325),fill='#66cccc');d.text((42,295),button,fill='black');img.save(path)
    reference={'index.html':f'<!doctype html><html><head><style>body{{background:{color};color:white;font-family:sans-serif}}.panel{{background:#eeeeee;color:black;padding:30px;border-radius:12px}}button{{background:#66cccc}}</style></head><body><h1>{title}</h1><section class="panel">No items yet</section><button>{button}</button></body></html>'}
    test=f'from pathlib import Path\nimport re\ns=Path("index.html").read_text()\nassert {title!r} in s\nassert {button!r} in s\nassert "No items yet" in s\nassert re.search(r"<button\\b",s,re.I)\nassert "background" in s.lower() and {color!r} in s.lower()\n'
    result={'id':f'hybrid-dev-{index:03d}','contract_id':f'visual-board-{variant}','category':'vision','request':f'Implement the attached reference as index.html, with heading {title}, empty panel text No items yet, and button {button}. Use background {color} and cyan button #66cccc; preserve reference layout.','expected_task_type':'VISION_ASSISTED_CODE','expected_suitable_workers':['vision','code'],'complexity':'medium','modality':'image','context':{'active_file':'index.html','workspace_available':True,'repository_scope':'file','initial_files':{'index.html':'<!doctype html><html><body>unfinished</body></html>'},'image_path':f'vision/{path.name}','image_sha256':hashlib.sha256(path.read_bytes()).hexdigest()},'allowed_change_paths':['index.html'],'sandbox_required':True,'execution_supported':True,'oracle':{'kind':'trusted_tests','trusted_files':{'test_contract.py':test},'command':['python','test_contract.py'],'expected_exit_code':0,'test_mount':'outside_editable_workspace','semantic_review_required':True,'limitations':'Structural text/style oracle does not establish visual fidelity; independent image review required.','success_endpoint':'READY_FOR_REVIEW'},'properties':{'typo':False,'followup':False,'ambiguous':False,'repair':False}}
    return result,reference


def build():
    cases=[];references={}
    for category,count,offset in [('explain',15,0),('edit',15,4),('debug',15,8),('implement',15,12),('refactor_multifile',10,2),('architecture',10,0),('context_heavy',10,10),('followup',5,15)]:
        for j in range(count):
            item,reference=case(len(cases)+1,category,SPECS[(offset+j)%len(SPECS)])
            cases.append(item);references[item['id']]=reference
    for j in range(5):
        item,reference=vision(len(cases)+1,j);cases.append(item);references[item['id']]=reference
    return cases,references


def main():
    cases,_=build()
    value={'schema_version':1,'authored_at':'2026-10-03','author':'hybrid development fixture agent','authorship_scope':'New contracts authored offline after viewing V2 development schema/examples. No held-out file or output read. Repeated contracts across task modes and generic task patterns correlate with V2; no claims of independent algorithms per case.','frozen':True,'cases':cases}
    raw=json.dumps(value,indent=2,ensure_ascii=False)+'\n';(ROOT/'main.json').write_text(raw,encoding='utf-8')
    entry={'file':'main.json','case_count':len(cases),'contract_clusters':len({c['contract_id'] for c in cases}),'canonical_sha256':hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),'file_sha256':hashlib.sha256((ROOT/'main.json').read_bytes()).hexdigest()}
    (ROOT/'provenance.json').write_text(json.dumps({'datasets':[entry],'heldout_access':False,'authoring_only_references':'References live only in author script; never model context.','vision_clusters_correlated':True},indent=2)+'\n',encoding='utf-8')
    print(json.dumps(entry))


if __name__=='__main__':main()
