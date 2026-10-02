"""Offline fixture authoring only; never imports product code or invokes workers."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parent
# Independent contracts: signature, requirement, trusted assertions.
SPECS = [
 ('clamp', 'value, low, high', 'Clamp value inclusively to low/high; raise ValueError when low exceeds high.', 'assert clamp(9,0,5)==5\nassert clamp(-1,0,5)==0\nassert clamp(3,0,5)==3'),
 ('median', 'values', 'Return the sorted middle value or average of two middle values; empty input raises ValueError; preserve input.', 'assert median([9,1,4])==4\nassert median([4,1])==2.5'),
 ('dedupe', 'values', 'Remove duplicates preserving first occurrence order, including unhashable lists.', 'assert dedupe([2,1,2])==[2,1]\nassert dedupe([[1],[1],[2]])==[[1],[2]]'),
 ('rotate', 'values, steps', 'Rotate list right by steps; negative steps rotate left; empty list returns empty.', 'assert rotate([1,2,3],1)==[3,1,2]\nassert rotate([1,2,3],-1)==[2,3,1]\nassert rotate([],9)==[]'),
 ('chunk', 'values, size', 'Return consecutive list chunks including short last chunk; size <=0 raises ValueError.', 'assert chunk([1,2,3],2)==[[1,2],[3]]\nassert chunk([],2)==[]'),
 ('is_prime', 'n', 'Return whether integer n is prime; numbers below two are false.', 'assert is_prime(2)\nassert is_prime(97)\nassert not is_prime(1)\nassert not is_prime(49)'),
 ('gcd', 'a, b', 'Return nonnegative greatest common divisor; gcd(0,0)=0.', 'assert gcd(-18,24)==6\nassert gcd(0,0)==0\nassert gcd(7,0)==7'),
 ('flatten', 'values', 'Flatten arbitrarily nested lists; non-list elements are preserved.', 'assert flatten([1,[2,[],[3]],4])==[1,2,3,4]\nassert flatten([])==[]'),
 ('word_counts', 'text', 'Count case-insensitive whitespace-separated words; punctuation stays part of words.', 'assert word_counts("A b a")=={"a":2,"b":1}\nassert word_counts("")=={}'),
 ('binary_search', 'values, target', 'Return leftmost target index in sorted list, or -1.', 'assert binary_search([1,2,2,4],2)==1\nassert binary_search([],3)==-1\nassert binary_search([1,3],2)==-1'),
 ('merge_ranges', 'ranges', 'Merge overlapping or touching closed numeric intervals, sorted by start; input preserved.', 'assert merge_ranges([(5,7),(1,3),(3,6)])==[(1,7)]\nassert merge_ranges([])==[]'),
 ('transpose', 'rows', 'Transpose rectangular matrix to lists; empty returns []; ragged raises ValueError.', 'assert transpose([[1,2],[3,4]])==[[1,3],[2,4]]\nassert transpose([])==[]'),
 ('balanced', 'text', 'Check balanced (), [], {} brackets, ignoring other characters.', 'assert balanced("a([{}])")\nassert not balanced("([)]")\nassert not balanced("(")'),
 ('slug', 'text', 'Lowercase ASCII text and replace each run of nonalphanumeric characters with hyphen; trim hyphens.', 'assert slug(" Hello, WORLD! ")=="hello-world"\nassert slug("---")==""'),
 ('running_total', 'values', 'Return prefix sums without modifying input.', 'assert running_total([2,-1,4])==[2,1,5]\nassert running_total([])==[]'),
 ('invert', 'mapping', 'Group original keys by their values in original insertion order.', 'assert invert({"a":1,"b":1,"c":2})=={1:["a","b"],2:["c"]}'),
 ('unique_pairs', 'values, total', 'Return sorted unique pairs (a,b), a<=b, summing to total; repeated value pair needs two occurrences.', 'assert unique_pairs([1,1,2,3,4],5)==[(1,4),(2,3)]\nassert unique_pairs([2],4)==[]'),
 ('rle', 'text', 'Return run-length encoding as list of (character,count) tuples.', 'assert rle("aaabbc")==[("a",3),("b",2),("c",1)]\nassert rle("")==[]'),
 ('parse_bool', 'text', 'Strip/casefold and accept true/yes/1 or false/no/0; invalid raises ValueError.', 'assert parse_bool(" YES ") is True\nassert parse_bool("0") is False'),
 ('distance', 'a, b', 'Return Levenshtein edit distance for strings using insertion/deletion/substitution.', 'assert distance("kitten","sitting")==3\nassert distance("","abc")==3\nassert distance("same","same")==0'),
]

def case(i, category, spec, split='main'):
    name, args, requirement, assertions = spec
    kind = {'explain':'EXPLAIN','edit':'EDIT','debug':'DEBUG','implement':'IMPLEMENT','refactor_multifile':'MULTI_FILE_CHANGE','architecture':'MULTI_FILE_CHANGE'}[category]
    initial = f'def {name}({args}):\n    raise NotImplementedError("unfinished")\n'
    expected = ['lightweight'] if category=='explain' else ['coder']
    prompt = f'Implement {name} in solution.py. {requirement}'
    oracle = {'kind':'trusted_tests','language':'python','trusted_files':{'test_contract.py':f'from solution import {name}\n{assertions}\n'},'command':['python','test_contract.py'],'expected_exit_code':0,'test_mount':'outside_editable_workspace','success_endpoint':'READY_FOR_REVIEW'}
    files={'solution.py':initial}
    if category=='explain':
        files={'solution.py':f'def {name}({args}):\n    """{requirement}"""\n    raise NotImplementedError("unfinished")\n'}
        prompt=f'Explain the contract and current behavior of {name} in this file. Is it implemented?'
        oracle={'kind':'human_rubric','required_facts':[requirement,'The implementation raises NotImplementedError rather than fulfilling the contract.'],'forbidden_claims':['The function currently passes its contract.'],'semantic_review_required':True,'success_endpoint':'ANSWERED'}
    elif category=='edit': prompt=f'creat the missing body for {name}; keep its public signature. {requirement}'
    elif category=='debug':
        files['solution.py']=f'def {name}({args}):\n    return None  # regression: stub accidentally shipped\n'
        prompt=f'fix teh regression in {name}. The test returns None where a result is required. {requirement}'
    elif category=='refactor_multifile':
        files['legacy.py']=initial
        files['solution.py']=f'from legacy import {name}\n'
        prompt=f'Refactor the unfinished {name} out of legacy.py into solution.py. Keep legacy.py as a backwards-compatible import. {requirement}'
        oracle['trusted_files']['test_contract.py']+=f'from legacy import {name} as old\nassert old is {name}\n'
    elif category=='architecture':
        expected=['reasoning','coder']
        prompt=f'Plan briefly, then implement {name} behind a service boundary: solution.py exports the function, service.py exports execute(payload), and cli.py reads one JSON payload from stdin and writes one JSON result. execute accepts keys {args}; preserve compatibility. {requirement}'
        files['service.py']='def execute(payload):\n    raise NotImplementedError\n'
        files['cli.py']='raise NotImplementedError\n'
        oracle['trusted_files']['test_contract.py']+='\nimport service, inspect\nassert callable(service.execute)\nassert "input(" not in inspect.getsource(service)\n'
        oracle['semantic_review_required']=True
        oracle['limitation']='Function assertions and service shape are executable; payload/CLI architecture needs independent human review and is not fully proven by these tests.'
    return {'id':f'{split}-{i:03d}','category':category,'request':prompt,'expected_task_type':kind,'expected_suitable_workers':expected,'complexity':'complex' if category=='architecture' else 'simple' if category in ('explain','edit') else 'medium','modality':'text','context':{'active_file':'solution.py','workspace_available':True,'repository_scope':'project' if category in ('architecture','refactor_multifile') else 'file','initial_files':files},'allowed_change_paths':list(files),'sandbox_required':category!='explain','execution_supported':True,'oracle':oracle}

def vision(i):
    return {'id':f'main-{i:03d}','category':'vision','request':['Fix the clipped submit button shown in this screenshot.','Use this screenshot to repair the overlapping mobile navigation.','Find and fix the unreadable error message shown here.','Fix teh misaligned table columns visible in the screenshot.','Repair the modal that extends beyond the viewport in this image.'][i-96],'expected_task_type':'VISION_ASSISTED_CODE','expected_suitable_workers':['vision','coder'],'complexity':'medium','modality':'image','context':{'workspace_available':False,'initial_files':{},'image_path':None},'sandbox_required':True,'execution_supported':False,'execution_limitation':'Independent screenshot and corresponding UI project not supplied; no synthetic substitute or success claim allowed.','oracle':{'kind':'unavailable','success_endpoint':'NOT_VERIFIED'}}

def freeze(filename, cases):
    value={'schema_version':1,'authored_at':'2026-10-02','author':'independent benchmark audit agent','authorship_scope':'Authored from master requirements and harness audit before inspecting subsequent router implementation; not derived from old 128 cases.','frozen':True,'cases':cases}
    canonical=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
    (ROOT/filename).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return {'file':filename,'case_count':len(cases),'canonical_sha256':hashlib.sha256(canonical).hexdigest(),'file_sha256':hashlib.sha256((ROOT/filename).read_bytes()).hexdigest()}

def main():
    main_cases=[]
    for category,count in [('explain',20),('edit',20),('debug',20),('implement',15),('refactor_multifile',15),('architecture',5)]:
        for j in range(count): main_cases.append(case(len(main_cases)+1,category,SPECS[j]))
    for index in (41,46,51,61,76,81):
        row=main_cases[index-1]
        original=row['request']
        row['history']=[{'role':'user','content':original},{'role':'assistant','content':'The requested function is unfinished; no patch has been accepted. Please confirm whether I should implement the specified contract.'}]
        row['request']=['fix that','continue','now make the tests pass'][index%3]
        row['context']['follow_up']=True
        row['context']['previous_request']=original
    main_cases += [vision(i) for i in range(96,101)]
    held_specs=[
      ('factorial','n','Return factorial for nonnegative integer; negative raises ValueError.','assert factorial(0)==1\nassert factorial(6)==720'),
      ('fib','n','Return nth Fibonacci with F0=0 F1=1; negative raises ValueError.','assert fib(0)==0\nassert fib(10)==55'),
      ('palindrome','text','Ignore whitespace and case only when checking palindrome.','assert palindrome("Never odd or even")\nassert not palindrome("ab")'),
      ('intersection','a, b','Return sorted unique integer intersection.','assert intersection([3,1,1],[1,2,3])==[1,3]'),
      ('suffixes','text','Return every nonempty suffix in descending length.','assert suffixes("abc")==["abc","bc","c"]\nassert suffixes("")==[]'),
      ('count_runs','values','Count consecutive runs of equal items.','assert count_runs([1,1,2,1])==3\nassert count_runs([])==0'),
      ('min_gap','values','Return minimum gap between sorted distinct integers, or None if fewer than two distinct values.','assert min_gap([9,1,4,4])==3\nassert min_gap([2,2]) is None'),
      ('zip_long','a, b','Zip lists to tuples padding missing values with None.','assert zip_long([1,2],[3])==[(1,3),(2,None)]'),
    ]
    held=[case(i+1,['debug','implement','refactor_multifile'][i//8],held_specs[i%8],split='heldout') for i in range(24)]
    provenance={'canonicalization':'UTF-8 JSON sort_keys=True separators=(comma,colon) ensure_ascii=False, excluding no fields','datasets':[freeze('main.json',main_cases),freeze('heldout.json',held)],'holdout_policy':'Do not inspect heldout prompts or assertions during tuning. Run once after policy and production hashes freeze; fixes require a new independent holdout.','limitations':['Main categories reuse contracts across task modes; report clustered confidence by contract, not 100 statistically independent algorithms.','Five vision cases deliberately lack assets and are unsupported; 95 main cases are executable or rubric-reviewable.','Assertions are narrow examples, not exhaustive correctness proof.','No fixture was executed against product or model during authoring.']}
    (ROOT/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(provenance))

if __name__=='__main__': main()
