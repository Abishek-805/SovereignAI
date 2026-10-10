"""Derive a leakage-free reference release; never change the canonical release."""
import collections, copy, hashlib, importlib.util, json, re, sys, zipfile
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from experiments.qlora_ready.audit import ROOT, RELEASE, FACTORY, MODEL, REVISION, rows, read, save, sha
from experiments.dataset_expansion.release import user_text, norm, shingles

def record_hash(row):
    return hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def scan(text):
    """Flag answer-bearing fields and worked-answer prose, including aliases."""
    findings=[]
    try: value=json.loads(text)
    except (ValueError,TypeError): value=None
    def walk(obj,path):
        if isinstance(obj,dict):
            for key,v in obj.items():
                normalized=re.sub(r'[^a-z]','',key.lower())
                if any(x in normalized for x in ('oracle','groundtruth','verifiedanswer','expected','precomputed','calculatorresult','calculatorobservation','answerlabel')) or normalized in {'answer','actual','result','solution','workedsolution'}:
                    findings.append({'path':path+'.'+key,'type':type(v).__name__,'reason':'answer-bearing field before a model action'})
                walk(v,path+'.'+key)
        elif isinstance(obj,list):
            for i,v in enumerate(obj):walk(v,f'{path}[{i}]')
    walk(value,'$')
    if re.search(r'(?i)(?:verified\s+answer|expected\s+(?:answer|result)|ground\s*truth|(?:correct\s+)?answer\s*[:=]|(?:expression|calculator)\s+(?:output|result)|\d\s*[+*/-]\s*\d[^\n]{0,40}(?:=|→)\s*[-+]?\d)',text):
        findings.append({'path':'$text','type':'str','reason':'worked-answer or answer-label prose'})
    return findings

def self_check():
    for s in ('{"answer":92}','{"verified_calculator_observations":[["73+19","92"]]}','73+19; answer=92','Expression result is 92','73 + 19 → 92','{"ground_truth": "ninety-two"}'):
        assert scan(s),s
    assert not scan('What is 73 + 19?')
    assert not scan('Use 1 MiB=1024 KiB. How long does the transfer take?')

def main():
    self_check()
    out=ROOT/'evidence/computation-leakage-repair'/datetime.now().strftime('%Y%m%d-%H%M%S');out.mkdir(parents=True,exist_ok=False)
    frozen={str(p.relative_to(RELEASE)):sha(p) for p in RELEASE.rglob('*') if p.is_file()}
    manifest=read(RELEASE/'final-release-manifest.json')
    assert all(sha(RELEASE/n)==d for n,d in manifest['artifacts_sha256'].items())
    assert all(sha(RELEASE/n)==d for n,d in manifest['raw_evidence_sha256'].items())
    original=rows(RELEASE/'positive-trajectories-final.jsonl'); adjusted=copy.deepcopy(original); originals={r['id']:r for r in original}
    changes=[];numeric_mentions=[]
    for row in adjusted:
        if row['category']!='computation':continue
        before=copy.deepcopy(row); prompt=row['messages'][1]['content']; value=json.loads(prompt)
        findings=scan(prompt)
        if not findings:continue
        assert set(value) in ({'question','verified_calculator_results'},{'question','verified_calculator_observations'})
        assert len(row['messages'])==3 and row['messages'][1]['role']=='user' and row['messages'][2]['role']=='assistant'
        assert not row.get('tools') and not any(m.get('tool_calls') for m in row['messages'])
        row['messages'][0]['content']='Answer the computation question using the quantities and units in the request. Do not claim to have used tools that were not invoked.'
        row['messages'][1]['content']=value['question']
        assert not scan(row['messages'][1]['content'])
        assert row['quality']==before['quality'] and row['source']==before['source'] and row['messages'][2:]==before['messages'][2:]
        changes.append({'id':row['id'],'split':row['release_checks']['split_assigned'],'original_prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'leakage':findings,'oracle_source':before['source'],'repair_strategy':'DIRECT_COMPUTATION_QA; retain exact source question and reference target, remove advance calculator answers; no fabricated model/tool trajectory','original_record_hash':record_hash(before),'adjusted_record_hash':record_hash(row),'adjustment_reason':'Answers supplied before model computation/action','adjustment_type':'MODEL_VISIBLE_INPUT_ONLY','provenance':'PUBLIC_REFERENCE' if before['source']['kind']=='public_human_reference' else 'PROGRAMMATIC_REFERENCE_OR_OPERATOR_AUTHORED; original source retained','expected_answer_unchanged':True})
        expected=Decimal(str(row['quality']['oracle']['expected']))
        occurrences=[m.group() for m in re.finditer(r'(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])',value['question']) if Decimal(m.group())==expected]
        if occurrences:
            assert row['id'] in {'gsm8k-11-semantic-reviewed','gsm8k-27-semantic-reviewed','gsm8k-37-semantic-reviewed'}
            numeric_mentions.append({'id':row['id'],'expected':str(expected),'occurrences':occurrences,'decision':'LEGITIMATE_INPUT_QUANTITY_NOT_ANSWER_DISCLOSURE','basis':{'gsm8k-11-semantic-reviewed':'$5 is a monthly allowance, not the requested driveway count.','gsm8k-27-semantic-reviewed':'400 is the number of additional downloads, not a stated total of retained files.','gsm8k-37-semantic-reviewed':'5 is the group/item count, not a stated per-person bill.'}[row['id']]})
    assert len(changes)==44
    changed={c['id'] for c in changes}; assert len(changed)==44
    assert all(r==originals[r['id']] for r in adjusted if r['id'] not in changed)
    for r in adjusted:
        if r['category']=='computation':assert not any(scan(m['content']) for m in r['messages'] if m['role'] in {'user','system'})
    splitmap={r['id']:s for s in ('train','validation','internal-test') for r in rows(RELEASE/(s+'.jsonl'))}
    splits={s:[r for r in adjusted if splitmap[r['id']]==s] for s in ('train','validation','internal-test')}
    assert {s:len(v) for s,v in splits.items()}=={'train':579,'validation':65,'internal-test':66}
    families=read(RELEASE/'split-assignment-final.json')['example_families'];seen=collections.defaultdict(set)
    for r in adjusted:
        for key in (families[r['id']],'declared:'+r['family'],*['article:'+e['title'] for e in r.get('evidence',[]) if 'title' in e]):seen[key].add(splitmap[r['id']])
        assert r['source']==originals[r['id']]['source'] and r['quality']==originals[r['id']]['quality']
        assert r['release_checks']['license_status'] in {'LICENSE_CONFIRMED','LICENSE_NOT_REQUIRED'}
        assert r['quality']['verified'] and r['quality']['oracle']['passed']
        path=r['quality']['oracle'].get('evidence')
        if path:assert (ROOT/path).is_file()
    assert all(len(v)==1 for v in seen.values())
    requests=[norm(user_text(r)) for r in adjusted];assert len(requests)==len(set(requests))
    words=[shingles(user_text(r)) for r in adjusted];pairs=[]
    for i,left in enumerate(adjusted):
        assert user_text(left)==user_text(originals[left['id']])
        for j in range(i+1,len(adjusted)):
            union=words[i]|words[j]; score=len(words[i]&words[j])/len(union) if union else 0
            if score<.6:continue
            right=adjusted[j];assert families[left['id']]==families[right['id']] and splitmap[left['id']]==splitmap[right['id']]
            assert (left['id'].startswith('mbpp-') and right['id'].startswith('mbpp-')) or (left['family']==right['family'] and left['id'].startswith('rc-') and right['id'].startswith('rc-'))
            pairs.append({'left':left['id'],'right':right['id'],'similarity':score,'classification':'SAME_SOURCE_FAMILY','cross_split':False})
    benchmark=ROOT/'evidence/dataset-expansion/20261008-133347/manifest.json'; expected=read(RELEASE/'acquisition-manifest.json')['T01_T15_acquisition_manifest_sha256'];assert sha(benchmark)==expected
    spec=importlib.util.spec_from_file_location('immutable_training',ROOT/'sovereignai-finetuning/training.py');training=importlib.util.module_from_spec(spec);spec.loader.exec_module(training)
    sys.path.insert(0,str(FACTORY/'format-runtime'));from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(FACTORY/'base-tokenizer',local_files_only=True,trust_remote_code=False)
    turns=[]
    for r in adjusted:
        encoded,rejected=training.tokenize_turns(tokenizer,[r],4096);assert encoded and not rejected
        pending=set()
        for m in r['messages']:
            assert m['role'] in {'system','user','assistant','tool'}
            for call in m.get('tool_calls',[]):assert call['id'] not in pending;pending.add(call['id']);assert isinstance(json.loads(call['function']['arguments']),dict)
            if m['role']=='tool':assert m['tool_call_id'] in pending;pending.remove(m['tool_call_id'])
        assert not pending
        for t in encoded:
            assert t['labels'][:t['prompt_tokens']]==[-100]*t['prompt_tokens'] and t['labels'][t['prompt_tokens']:]==t['input_ids'][t['prompt_tokens']:]
            assert len(t['input_ids'])<=4096 and t['assistant_tokens']>0
            turns.append({'id':r['id'],'split':splitmap[r['id']],'turn':t['turn'],'tokens':len(t['input_ids']),'prompt_tokens':t['prompt_tokens'],'assistant_tokens':t['assistant_tokens'],'adjusted':r['id'] in changed})
    def jsonl(path,values):path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in values),encoding='utf-8')
    for s,v in splits.items():jsonl(out/(s+'.adjusted.jsonl'),v)
    jsonl(out/'adjusted-computation-records.jsonl',[r for r in adjusted if r['id'] in changed])
    save(out/'computation-leakage-audit.json',{'known_affected':43,'new_equivalent_leakage':1,'new_record':'computation-binary-transfer','total_repaired':44,'affected_by_split':dict(collections.Counter(c['split'] for c in changes)),'changes':changes,'remaining_leakage':0,'legitimate_numeric_mentions_reviewed':numeric_mentions,'scanner_controls':'PASS','scanner_limit':'Rule-based structural/phrase triage plus source-question preservation and explicit numeric-collision review; not a universal semantic-leak detector.'})
    save(out/'information-boundary-audit.json',{'status':'PASS','fields':{'messages.system_and_user':'MODEL_VISIBLE','messages.assistant':'TRAINING_TARGET; generated during evaluation, not supplied in initial prompt','messages.tool':'MODEL_VISIBLE after linked assistant action only','tools':'MODEL_VISIBLE','quality.oracle':'EVALUATOR_ONLY','source':'PROVENANCE_ONLY','curation_metadata':'TRAINING_METADATA','release_checks':'TRAINING_METADATA','family_and_difficulty':'TRAINING_METADATA','initial_state':'TASK_FIXTURE; expose only through authorized context/tools','final_diff':'EVALUATOR_ONLY'},'records':[{'id':r['id'],'field_paths':{key:('MODEL_VISIBLE_OR_TRAINING_TARGET' if key in {'messages','tools'} else 'EVALUATOR_ONLY' if key in {'quality','final_diff'} else 'PROVENANCE_ONLY' if key=='source' else 'TRAINING_METADATA_OR_TASK_FIXTURE') for key in r}} for r in adjusted],'no_full_row_serialization_into_prompt':True,'reference_targets_not_claimed_as_model_success':True})
    save(out/'tokenizer-adjusted-audit.json',{'status':'PASS','model':MODEL,'revision':REVISION,'all_examples':710,'adjusted_examples':44,'assistant_turns':len(turns),'all_loss_masks_checked':True,'tool_linkage_checked':True,'truncated':0,'max_tokens':max(t['tokens'] for t in turns),'turns':turns})
    save(out/'semantic-contamination-recheck.json',{'status':'PASS','requests_unchanged':True,'exact_duplicates':0,'cross_split_flags':0,'pairs':pairs,'historical_semantic_review_sha256':sha(RELEASE/'semantic-isolation-review.json'),'T01_T15_contents_not_inspected':True,'latent_similarity_not_proven_absent':True})
    save(out/'dataset-integrity-recheck.json',{'status':'PASS','counts':{s:len(v) for s,v in splits.items()},'total':710,'unchanged_examples':666,'changed_examples':44,'family_isolation':'PASS','licenses':'PASS','source_oracles_targets_unchanged':'PASS','role_tool_integrity':'PASS','oracle_boundary':'PASS','tokenizer_and_masks':'PASS','semantic_isolation':'PASS','benchmark_integrity':'PASS','benchmark_manifest_sha256':expected,'benchmark_contents_inspected':False,'model_evaluation_run':False,'training_run':False})
    assert all(sha(RELEASE/n)==d for n,d in frozen.items()) and sha(benchmark)==expected
    (out/'FINAL_REPORT.md').write_text('# Computation leakage repair\n\nStatus: FORMAT_GATE_RECOVERED\n\nRepaired 43 known GSM8K records and one additionally detected record, computation-binary-transfer, which exposed answers under verified_calculator_observations. All 44 are direct computation reference QA now. No fabricated tool calls or local-model successes. Exact source questions, targets, source/license/oracle metadata, IDs, families and split assignments are preserved. The other 666 records are identical.\n\n710 records: 579 train / 65 validation / 66 internal-test. All 1010 assistant-turn boundaries/masks checked with the official pinned tokenizer; no truncation. Zero remaining observed computation answer leakage. Three numeric answer/input coincidences were reviewed as legitimate task quantities. Exact duplicate, source/family isolation and pair triage checks pass; unflagged latent similarities are not proven absent.\n\nThe canonical release, raw history and benchmark manifest hashes are unchanged. No T01–T15 prompts, outputs, solutions or outcomes inspected. No Base evaluation, model load, smoke, training or checkpoints executed. Colab cells are preparation only; the earlier environment probe was run before the current instruction and is not a training-compatibility result.\n',encoding='utf-8')
    save(out/'release-manifest-adjusted.json',{'status':'FORMAT_GATE_RECOVERED','release_gate':'PASS','canonical_namespace':str(RELEASE),'canonical_artifact_hashes':frozen,'model':MODEL,'revision':REVISION,'counts':{s:len(v) for s,v in splits.items()},'adjusted_record_count':44,'original_requested_count':43,'additional_equivalent_leakage_discovered':1,'canonical_overwrite_allowed':False,'baseline_run':False,'training_run':False,'RUN_TRAIN':False,'artifact_sha256':{p.name:sha(p) for p in out.iterdir() if p.is_file()},'repair_script_sha256':sha(Path(__file__))})
    print(json.dumps({'namespace':str(out),'status':'FORMAT_GATE_RECOVERED','repaired':44,'unchanged':666,'counts':{s:len(v) for s,v in splits.items()},'max_tokens':max(t['tokens'] for t in turns)}))

if __name__=='__main__':main()
