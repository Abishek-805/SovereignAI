"""Isolated readiness probes; deliberately exposes no full-training action."""
import argparse
import collections
import gc
import hashlib
import json
import os
import shutil
import time
import sys
from pathlib import Path
import readiness as r

original_acquire = r.acquire
original_environment = r.environment
CONFIG_SHA = 'ddc63e1c717afa86c865bb5e01313d89d72bb53b97ad4a8a03ba8510c0621670'
SHARDS = {'model.safetensors-00001-of-00002.safetensors':'df547074dce70532a0493e5433152bd17a65efb89088cfabc2e7e2371a93d712',
          'model.safetensors-00002-of-00002.safetensors':'590fbaac095dd31db886c322d9d2f7df47777966391acf306ddddc3e4e3a15ef'}


def acquire(data, out):
    directory = original_acquire(data, out)
    assert r.digest(directory/'config.json') == CONFIG_SHA
    assert r.read(out/'base-model-identity.json')['safetensors_sha256'] == SHARDS
    r.save(out/'model-verification.json', {'status':'PASS','config_sha256':CONFIG_SHA,
           'native_shards':SHARDS,'tokenizer_hashes':r.read(data/'package-manifest.json')['tokenizer_files']})
    return directory


def environment(out):
    result = original_environment(out)
    import torch
    result['bf16_native_supported'] = torch.cuda.is_bf16_supported(including_emulation=False)
    result['bf16_with_emulation_supported'] = torch.cuda.is_bf16_supported(including_emulation=True)
    result['generation_settings'] = {'seed':42,'do_sample':False,'max_new_tokens_baseline':4096,
                                    'strict_all_cuda_kernels_deterministic':False}
    r.save(out/'colab-environment-report.json', result)
    return result


r.acquire = acquire
r.environment = environment


def atomic(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    r.save(temporary, value)
    os.replace(temporary, path)


def expected(data):
    splits = r.integrity(data)
    return [(s, row) for s in ('validation', 'internal-test') for row in splits[s]]


def validate_predictions(data, predictions, complete=False):
    wanted = {(s, row['id']): row for s, row in expected(data)}
    keys = [(v['split'], v['id']) for v in predictions]
    assert len(keys) == len(set(keys)), 'Duplicate prediction IDs'
    assert set(keys) <= set(wanted), 'Unexpected prediction IDs'
    for v in predictions:
        row = wanted[(v['split'], v['id'])]
        assert v['model'] == r.MODEL and v['revision'] == r.REVISION and v['adapter'] is None
        assert v['category'] == row['category']
        assert v['dataset_sha256'] == r.digest(data/(v['split']+'.adjusted.jsonl'))
        assert v['code_executed'] is False and v['independent_status'] == 'NOT_TESTED'
        assert isinstance(v['raw_output'], str) and v['generated_tokens'] > 0
    missing = sorted(set(wanted)-set(keys))
    if complete:
        assert not missing and len(predictions) == 131, ('Missing predictions', missing)
    return missing


def baseline(data, out):
    checkpoint = out/'records'
    checkpoint.mkdir(exist_ok=True)
    predictions = []
    for file in sorted(checkpoint.glob('*.json')):
        saved = r.read(file)
        canonical = json.dumps(saved['prediction'], sort_keys=True, ensure_ascii=False).encode()
        assert hashlib.sha256(canonical).hexdigest() == saved['sha256'], 'Checkpoint corrupted'
        predictions.append(saved['prediction'])
    validate_predictions(data, predictions)
    done = {(v['split'], v['id']) for v in predictions}
    ordered = expected(data)
    if len(done) < 131:
        model, tokenizer, loading = r.load(r.acquire(data, out))
        model.eval()
        for split, row in ordered:
            if (split, row['id']) in done:
                continue
            first = next(i for i, m in enumerate(row['messages']) if m['role'] == 'assistant')
            result = {'id':row['id'], 'split':split, 'category':row['category'],
                      'model':r.MODEL, 'revision':r.REVISION, 'adapter':None,
                      'dataset_sha256':r.digest(data/(split+'.adjusted.jsonl')),
                      'scope':'first assistant response only; agentic full rollout still required',
                      'code_executed':False, 'independent_status':'NOT_TESTED',
                      **r.generate(model, tokenizer, row['messages'][:first], row.get('tools'))}
            name = hashlib.sha256((split+'\0'+row['id']).encode()).hexdigest()+'.json'
            assert not (checkpoint/name).exists(), 'Never overwrite a checkpoint'
            canonical = json.dumps(result, sort_keys=True, ensure_ascii=False).encode()
            atomic(checkpoint/name, {'prediction':result, 'sha256':hashlib.sha256(canonical).hexdigest()})
            predictions.append(result)
            atomic(out/'base-predictions.json', predictions)
            print(f'{len(predictions)}/131 {split} {row["id"]}: captured, not independently validated', flush=True)
        del model, tokenizer
        gc.collect()
        import torch
        torch.cuda.empty_cache()
        r.save(out/'baseline-load.json', loading)
    by_key = {(v['split'], v['id']):v for v in predictions}
    predictions = [by_key[(s,row['id'])] for s,row in ordered]
    missing = validate_predictions(data, predictions, complete=True)
    atomic(out/'base-predictions.json', predictions)
    counts = dict(collections.Counter(v['split'] for v in predictions))
    categories = {s:dict(collections.Counter(v['category'] for v in predictions if v['split']==s)) for s in counts}
    r.save(out/'baseline-counts.json', {'status':'PASS', 'captured':len(predictions),
           'counts':counts, 'missing':missing, 'duplicates':0, 'categories':categories,
           'prediction_sha256':r.digest(out/'base-predictions.json'), 'independent_status':'NOT_TESTED'})
    (out/'independent-review-checklist.md').write_text(
        'Raw capture is not correctness. Review all 65 validation and 66 internal-test records.\n'
        'RAG: source-bound semantic review. Coding: existing Docker-only oracles.\n'
        'Agentic: full stateful tool rollouts in Docker. Computation/safety/summarization: unchanged evaluators.\n'
        'No keyword-only scoring. Bind each result to ID, category, prediction/dataset/evidence hashes.\n', encoding='utf-8')


def encoded_train(data, tokenizer, out):
    from colab_format_helpers import tokenize_turns
    turns, rejected = tokenize_turns(tokenizer, r.integrity(data)['train'], 4096)
    assert not rejected, 'Oversize records: do not truncate'
    lengths = sorted(len(v['input_ids']) for v in turns)
    assert turns and max(lengths) <= 4096
    assert all(len(v['input_ids']) == len(v['labels']) == len(v['attention_mask']) for v in turns)
    assert all(any(n != -100 for n in v['labels']) for v in turns)
    r.save(out/'training-tokenization.json', {'turns':len(turns),'min':min(lengths),'max':max(lengths),
           'percentiles':{str(p):lengths[round((len(lengths)-1)*p/100)] for p in (50,90,95,99)},
           'oversize_count':len(rejected),'truncated_count':0,'assistant_only_official_template':True})
    return turns


def frozen_hashes(model):
    # Hash one tensor at a time to avoid a second full Base in host memory.
    return {n:hashlib.sha256(p.detach().cpu().contiguous().view(-1).view(__import__('torch').uint8).numpy().tobytes()).hexdigest()
            for n,p in model.named_parameters() if not p.requires_grad}


def probe(data, out, fit=False):
    import torch
    from peft import PeftModel
    directory = r.acquire(data, out)
    model, tokenizer, loading = r.adapter_model(directory)
    turns = encoded_train(data, tokenizer, out)
    turn = (max if fit else min)(turns, key=lambda v:len(v['input_ids']))
    inputs = r.batch(turn, length=4096 if fit else None)
    assert inputs['input_ids'].shape[1] == (4096 if fit else len(turn['input_ids']))
    model.train()
    adapters = {n:p for n,p in model.named_parameters() if p.requires_grad}
    assert adapters and all('lora_' in n for n in adapters)
    before = {n:p.detach().cpu().clone() for n,p in adapters.items()}
    frozen = frozen_hashes(model)
    optimizer = torch.optim.AdamW(adapters.values(), lr=1e-4)
    started = time.perf_counter()
    torch.cuda.reset_peak_memory_stats()
    loss = model(**inputs).loss
    assert torch.isfinite(loss)
    forward = r.memory()
    loss.backward()
    backward = r.memory()
    assert all(p.grad is None or torch.isfinite(p.grad).all() for p in adapters.values())
    assert any(p.grad is not None and p.grad.abs().sum()>0 for p in adapters.values())
    assert all(p.grad is None for n,p in model.named_parameters() if n not in adapters)
    torch.nn.utils.clip_grad_norm_(adapters.values(),1.0)
    optimizer.step()
    step_memory = r.memory()
    assert all(torch.isfinite(p).all() for p in adapters.values()), 'Non-finite adapter parameters'
    assert any(not torch.equal(before[n],p.detach().cpu()) for n,p in adapters.items())
    assert frozen == frozen_hashes(model), 'Frozen Base parameters changed'
    result = {'status':'PASS','model':r.MODEL,'revision':r.REVISION,'load':loading,
              'forward':forward,'backward':backward,'optimizer':step_memory,
              'seconds':time.perf_counter()-started,'loss':float(loss.detach().cpu()),
              'base_frozen_hash_verified':True,'adapter_gradients_verified':True,
              'adapter_parameters_changed':True,'source_train_id':turn['id'],
              'actual_tokens':int(inputs['input_ids'].shape[1]),'full_training_run':False,
              'precision':loading['precision'],'single_disposable_optimizer_step':True}
    disposable = out/'temporary-smoke-adapter'
    if not fit:
        assert not disposable.exists()
        model.save_pretrained(disposable)
        result['disposable_adapter_hashes'] = {str(f.relative_to(disposable)):r.digest(f) for f in disposable.rglob('*') if f.is_file()}
    del loss, inputs, optimizer, before, adapters, model, tokenizer
    gc.collect();torch.cuda.empty_cache()
    if not fit:
        fresh, tokenizer, _ = r.load(directory)
        reloaded = PeftModel.from_pretrained(fresh, disposable, is_trainable=False)
        reloaded.eval()
        with torch.no_grad():
            reload_loss = reloaded(**r.batch(turn)).loss
        assert torch.isfinite(reload_loss)
        result['reload_loss'] = float(reload_loss.cpu())
        result['fresh_base_adapter_reload'] = 'PASS'
        del reload_loss, reloaded, fresh, tokenizer
        gc.collect();torch.cuda.empty_cache()
        assert disposable.resolve().is_relative_to(out.resolve())
        shutil.rmtree(disposable)
        result['disposable_adapter_cleaned'] = True
    else:
        result.update(candidate_length=4096, actual_training_turn_tokens=len(turn['input_ids']),
                      synthetic_padding_for_fit_probe_only=True, canonical_dataset_modified=False)
    r.save(out/('sequence-fit-result.json' if fit else 'qlora-smoke-result.json'),result)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('stage',choices=['environment','integrity','acquire','base-load','base-smoke','baseline','qlora-smoke','fit'])
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(a.data))
    if a.stage=='environment':r.environment(a.output)
    elif a.stage=='integrity':
        r.integrity(a.data);r.save(a.output/'dataset-integrity.json',{'status':'PASS','counts':{'train':579,'validation':65,'internal-test':66}})
    elif a.stage=='acquire':r.acquire(a.data,a.output)
    elif a.stage=='base-load':
        model,tokenizer,loading=r.load(r.acquire(a.data,a.output))
        r.save(a.output/'base-load-result.json',{'status':'PASS',**loading})
        del model,tokenizer;gc.collect();__import__('torch').cuda.empty_cache()
    elif a.stage=='base-smoke':r.base_smoke(a.data,a.output)
    elif a.stage=='baseline':baseline(a.data,a.output)
    else:
        try:probe(a.data,a.output,fit=a.stage=='fit')
        finally:
            disposable=a.output/'temporary-smoke-adapter'
            if disposable.exists():
                assert disposable.resolve().is_relative_to(a.output.resolve())
                shutil.rmtree(disposable)
                r.save(a.output/'disposable-cleanup.json',{'removed':True,'full_training_run':False})


if __name__=='__main__':
    try:main()
    except Exception as exc:
        import traceback
        # CLI output is explicit and bounded by the trusted notebook stage runner.
        output=Path(sys.argv[sys.argv.index('--output')+1])
        r.save(output/'stage-failure.json',{'status':'FAIL','stage':sys.argv[1],
               'error_type':type(exc).__name__,'error':repr(exc),'traceback':traceback.format_exc(),
               'OOM':type(exc).__name__=='OutOfMemoryError' or 'out of memory' in str(exc).lower(),
               'automatic_fallback':False,'full_training_run':False})
        raise
