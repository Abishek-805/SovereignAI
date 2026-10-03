"""Separately authored holdout. Do not open this file while tuning runtime policy."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SPECS=[
 ('xor_reduce','values','Return integer XOR of every value; empty returns 0.','out=0\nfor v in values: out^=v\nreturn out','assert xor_reduce([3,5,3])==5\nassert xor_reduce([])==0'),
 ('hamming','a, b','Count differing positions in equal-length strings; unequal lengths raises ValueError.','if len(a)!=len(b):raise ValueError\nreturn sum(x!=y for x,y in zip(a,b))','assert hamming("10101","10011")==2'),
 ('title_ascii','text','Capitalize first ASCII character of each whitespace-separated word; lowercase remaining characters.','return " ".join(w[0].upper()+w[1:].lower() for w in text.split())','assert title_ascii("aDA LOVELACE")=="Ada Lovelace"'),
 ('nth_from_end','values, n','Return nth item from end, n counting from one; invalid n raises IndexError.','if n<1 or n>len(values):raise IndexError\nreturn values[-n]','assert nth_from_end([4,7,9],2)==7'),
 ('pairwise_products','values','Return products of adjacent pairs.','return [a*b for a,b in zip(values,values[1:])]','assert pairwise_products([2,3,4])==[6,12]'),
 ('sum_squares','values','Return sum of squares of numeric values.','return sum(v*v for v in values)','assert sum_squares([-2,3])==13'),
 ('strip_suffix_once','text, suffix','Remove suffix exactly once, empty suffix leaves text unchanged.','return text[:-len(suffix)] if suffix and text.endswith(suffix) else text','assert strip_suffix_once("report.txt.txt",".txt")=="report.txt"\nassert strip_suffix_once("abc","")=="abc"'),
 ('quote_csv','field','Always quote string as a CSV field, doubling any inner double quotes.','return chr(34)+field.replace(chr(34),chr(34)*2)+chr(34)','assert quote_csv(\'a"b\')==\'"a""b"\''),
 ('stable_minima','values','Return indices of all minimum values; empty returns [].','return [i for i,v in enumerate(values) if v==min(values)] if values else []','assert stable_minima([3,1,2,1])==[1,3]'),
 ('range_step','start, stop, step','Return list of Python range values; step zero raises ValueError.','return list(range(start,stop,step))','assert range_step(5,-1,-2)==[5,3,1]'),
 ('greater_count','values, threshold','Count values strictly greater than threshold.','return sum(v>threshold for v in values)','assert greater_count([2,3,4],3)==1'),
 ('absolute_sum','values','Return sum of absolute values.','return sum(abs(v) for v in values)','assert absolute_sum([-4,2,-1])==7'),
 ('mod_histogram','values, modulus','Count integer values by modulo bucket; modulus<=0 raises ValueError.','if modulus<=0:raise ValueError\nout={}\nfor v in values: r=v%modulus;out[r]=out.get(r,0)+1\nreturn out','assert mod_histogram([-1,0,3],3)=={2:1,0:2}'),
 ('nonempty_values','mapping','Return new mapping dropping None and empty strings, but retain zero and False.','return {k:v for k,v in mapping.items() if v is not None and v!=""}','assert nonempty_values({"a":None,"b":"","c":0,"d":False})=={"c":0,"d":False}'),
 ('swap_values','mapping, first, second','Return copy swapping values of two existing keys; missing key raises KeyError.','out=dict(mapping);out[first],out[second]=out[second],out[first];return out','assert swap_values({"a":1,"b":2},"a","b")=={"a":2,"b":1}'),
 ('group_lengths','words','Group words by length, preserve original order within each bucket.','out={}\nfor word in words:out.setdefault(len(word),[]).append(word)\nreturn out','assert group_lengths(["a","bb","c"])=={1:["a","c"],2:["bb"]}'),
 ('move_first','values, target','Return copy moving first matching target to front; missing target preserves list.','out=list(values)\nif target in out:out.insert(0,out.pop(out.index(target)))\nreturn out','assert move_first([1,2,3,2],2)==[2,1,3,2]'),
 ('window_average','values, size','Return average of each full sliding window; size<=0 raises ValueError.','if size<=0:raise ValueError\nreturn [sum(values[i:i+size])/size for i in range(len(values)-size+1)]','assert window_average([1,3,5],2)==[2,4]'),
 ('wrap_index','index, size','Return index modulo positive size; size<=0 raises ValueError.','if size<=0:raise ValueError\nreturn index%size','assert wrap_index(-1,4)==3'),
 ('ordinal_suffix','n','Return English ordinal suffix using absolute integer, including 11/12/13 exceptions.','n=abs(n)\nreturn "th" if 10<n%100<14 else {1:"st",2:"nd",3:"rd"}.get(n%10,"th")','assert ordinal_suffix(11)=="th"\nassert ordinal_suffix(22)=="nd"'),
 ('repeat_each','values, times','Repeat each item times times; negative times returns empty.','return [v for v in values for _ in range(max(0,times))]','assert repeat_each([1,2],2)==[1,1,2,2]'),
 ('ascii_letters','text','Return only ASCII letters, preserving original case.','return "".join(c for c in text if "a"<=c<="z" or "A"<=c<="Z")','assert ascii_letters("éA1z_")=="Az"'),
 ('join_nonempty','parts, separator','Join nonempty strings; skip empty strings but retain whitespace strings.','return separator.join(p for p in parts if p!="")','assert join_nonempty(["a",""," ","b"],"|")=="a| |b"'),
 ('lookup_path','mapping, keys','Follow nested mapping keys; return None when any key missing.','current=mapping\nfor key in keys:\n if not isinstance(current,dict) or key not in current:return None\n current=current[key]\nreturn current','assert lookup_path({"a":{"b":4}},["a","b"])==4\nassert lookup_path({},["a"]) is None'),
]

def main():
    cases=[]
    for i,(name,args,requirement,body,checks) in enumerate(SPECS,1):
        category=['debug','implement','refactor_multifile'][(i-1)//8]
        files={'solution.py':f'def {name}({args}):\n    return None\n'}
        request=f'{"Fix" if category=="debug" else "Implement"} {name} in solution.py. {requirement}'
        if category=='refactor_multifile':
            files={'legacy.py':files['solution.py'],'solution.py':f'from legacy import {name}\n'}
            request=f'Refactor {name} into solution.py, leaving legacy.py as a compatibility import; implement this behavior: {requirement}'
            checks+=f'\nfrom legacy import {name} as old\nassert old is {name}'
        cases.append({'id':f'v2-heldout-{i:03d}','contract_id':name,'category':category,'request':request,'expected_task_type':{'debug':'DEBUG','implement':'IMPLEMENT','refactor_multifile':'MULTI_FILE_CHANGE'}[category],'expected_suitable_workers':['code'],'complexity':'medium' if category=='refactor_multifile' else 'simple','modality':'text','context':{'active_file':'solution.py','workspace_available':True,'repository_scope':'project' if category=='refactor_multifile' else 'file','initial_files':files},'allowed_change_paths':list(files),'sandbox_required':True,'execution_supported':True,'oracle':{'kind':'trusted_tests','language':'python','trusted_files':{'test_contract.py':f'from solution import {name}\n{checks}\n'},'command':['python','test_contract.py'],'expected_exit_code':0,'test_mount':'outside_editable_workspace','success_endpoint':'READY_FOR_REVIEW'}})
    data={'schema_version':1,'authored_at':'2026-10-03','author':'independent V2 fixture author agent, separate holdout authoring pass','authorship_scope':'Distinct V2 heldout contracts separately authored without reading old heldout.json or benchmark results. Initial old schema-authoring script inspection exposed embedded legacy contract definitions; no legacy contract or result was reused. Not supplied to runtime tuner. No models or production routing imported.','frozen':True,'cases':cases}
    (ROOT/'heldout.json').write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    entry={'file':'heldout.json','case_count':len(cases),'canonical_sha256':hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),'file_sha256':hashlib.sha256((ROOT/'heldout.json').read_bytes()).hexdigest()}
    development=json.loads((ROOT/'development-freeze.json').read_text(encoding='utf-8'))
    provenance={'schema_version':1,'datasets':[development,entry],'holdout_policy':'Runtime tuning may inspect development only. Freeze production/harness/configuration before first heldout execution. Do not tune using heldout failures; a new policy needs a separately authored new holdout.','limitations':['Development has 100 task cases over 35 distinct computational contracts plus five vision contracts. Repeated computational contracts across modes are correlated; cluster statistical intervals by contract_id.','20 explanation tasks and one ambiguous edit require independent semantic review.','Five actual PNG UI references are authored bitmaps, not browser screenshots; executable structure/style checks do not prove visual fidelity.','Holdout has 24 distinct contracts, but only debugging/implementation/refactoring. No heldout explanation, architecture, or vision quality estimate.','Initial legacy authoring script inspection exposed embedded old heldout contract definitions. Old heldout.json and old model outputs were not opened. V2 contracts are distinct, but authorship was not blind to every old contract definition.','Oracle examples are not exhaustive correctness proofs. All generation context excludes trusted_files and author reference solutions.']}
    (ROOT/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'heldout_freeze':entry}))

if __name__=='__main__':main()
