"""One isolated 4096-token disposable update; never exposes full training."""
import argparse
import gc
import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

CONFIGS = {
    'baseline': {},
    'sdpa': {'attention': 'sdpa'},
    'nonreentrant': {'nonreentrant': True},
    'paged8bit': {'optimizer': 'paged_adamw_8bit'},
    'allocator': {'allocator': 'expandable_segments:True'},
    'supervised_logits': {'loss_positions': 'supervised_only'},
    'sdpa_nonreentrant': {'attention': 'sdpa', 'nonreentrant': True},
    'sdpa_paged8bit': {'attention': 'sdpa', 'optimizer': 'paged_adamw_8bit'},
}


def verify_supervised_logits():
    import torch
    from transformers.loss.loss_utils import ForCausalLMLoss
    logits = torch.randn(1,9,11,requires_grad=True)
    labels = torch.tensor([[-100,-100,3,7,-100,2,-100,5,-100]])
    shift = torch.nn.functional.pad(labels,(0,1),value=-100)[:,1:]
    positions = torch.where(shift[0]!=-100)[0]
    full = ForCausalLMLoss(logits,labels,11)
    reduced = ForCausalLMLoss(logits[:,positions],labels,11,shift_labels=shift[:,positions])
    assert torch.allclose(full,reduced,atol=1e-6)
    first = torch.autograd.grad(full,logits,retain_graph=True)[0]
    second = torch.autograd.grad(reduced,logits)[0]
    assert torch.allclose(first,second,atol=1e-6)
    return {'loss_equivalence':'PASS','logit_gradient_equivalence':'PASS',
            'disjoint_labels_and_ignored_final_position':True}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('configuration', choices=CONFIGS)
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    changes = CONFIGS[a.configuration]
    if 'allocator' in changes:
        os.environ['PYTORCH_ALLOC_CONF'] = changes['allocator']
    sys.path.insert(0, str(a.data))
    import worker as w
    import torch
    from peft import PeftModel
    r = w.r
    config = dict(sequence_length=4096, microbatch=1, accumulation_probe=1,
                  planned_training_accumulation=16, gradient_checkpointing=True,
                  nonreentrant=False, attention='eager', optimizer='adamw_torch',
                  lr=1e-4, rank=16, alpha=32, dropout=.05, seed=42,
                  quantization='NF4 double quant', precision='torch.bfloat16',
                  full_training=False, RUN_TRAIN=False, **{})
    config.update(changes)
    result = dict(status='RUNNING', configuration=config, model=r.MODEL,
                  revision=r.REVISION, forward_success=False, backward_success=False,
                  optimizer_success=False, OOM=False, loss=None, full_training=False)
    start = time.perf_counter()
    disposable = a.output/'disposable-adapter'

    def record(stage):
        result['stage'] = stage
        result['elapsed_seconds'] = time.perf_counter()-start
        result['memory'] = r.memory()
        result['cpu_rss_bytes'] = __import__('psutil').Process().memory_info().rss
        result.setdefault('measurements', []).append(dict(stage=stage, memory=result['memory'],
                cpu_rss_bytes=result['cpu_rss_bytes'], elapsed_seconds=result['elapsed_seconds']))
        r.save(a.output/'result.json', result)
        print(stage, json.dumps(result['memory']), flush=True)

    try:
        r.environment(a.output)
        if config.get('loss_positions') == 'supervised_only':
            result['objective_selfcheck'] = verify_supervised_logits()
        r.integrity(a.data)
        files = r.read(a.data/'package-manifest.json')['files']
        before_data = {name:r.digest(a.data/name) for name in files}
        r.save(a.output/'dataset-hashes-before.json', before_data)
        directory = r.acquire(a.data, a.output)
        if config['attention'] != 'eager':
            original_load = r.load
            def load(directory):
                # Reuse the exact pinned loader, changing only its documented attention setting.
                import inspect
                source = inspect.getsource(original_load).replace("attn_implementation='eager'", "attn_implementation='sdpa'")
                scope = dict(original_load.__globals__)
                exec(compile(source, '<isolated-sdpa-loader>', 'exec'), scope)
                return scope['load'](directory)
            r.load = load
        model, tokenizer, loading = r.adapter_model(directory)
        if config['nonreentrant']:
            model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
        result['loading'] = loading
        result['effective_checkpointing'] = model.is_gradient_checkpointing
        result['attention_configs'] = {n:str(m.config._attn_implementation) for n,m in model.named_modules()
                                      if hasattr(m,'config') and hasattr(m.config,'_attn_implementation')}
        turns = w.encoded_train(a.data, tokenizer, a.output)
        turn = max(turns, key=lambda v:len(v['input_ids']))
        inputs = r.batch(turn, length=4096)
        assert inputs['input_ids'].shape == (1,4096)
        forward_kwargs = {}
        if config.get('loss_positions') == 'supervised_only':
            # Ignored labels contribute no loss; retain their full input context but skip unused vocabulary logits.
            shift = torch.nn.functional.pad(inputs['labels'], (0,1), value=-100)[:,1:]
            positions = torch.where(shift[0] != -100)[0]
            assert positions.numel()>0
            forward_kwargs = dict(logits_to_keep=positions, shift_labels=shift[:,positions])
            result['supervised_logit_positions'] = positions.numel()
        result.update(source_train_id=turn['id'], source_tokens=len(turn['input_ids']),
                      synthetic_unlabelled_padding_only=True, truncated_count=0)
        model.train()
        adapters = {n:p for n,p in model.named_parameters() if p.requires_grad}
        assert adapters and all('lora_' in n for n in adapters)
        before = {n:p.detach().cpu().clone() for n,p in adapters.items()}
        frozen = w.frozen_hashes(model)
        if config['optimizer']=='paged_adamw_8bit':
            from bitsandbytes.optim import PagedAdamW8bit
            optimizer = PagedAdamW8bit(adapters.values(), lr=1e-4)
        else:
            optimizer = torch.optim.AdamW(adapters.values(), lr=1e-4)
        torch.cuda.reset_peak_memory_stats()
        record('forward_started')
        loss = model(**inputs, **forward_kwargs).loss
        assert torch.isfinite(loss)
        result.update(forward_success=True, loss=float(loss.detach().cpu()))
        record('forward_complete')
        loss.backward()
        result['backward_success'] = True
        record('backward_complete')
        assert all(p.grad is None or torch.isfinite(p.grad).all() for p in adapters.values())
        assert any(p.grad is not None and p.grad.abs().sum()>0 for p in adapters.values())
        assert all(p.grad is None for n,p in model.named_parameters() if n not in adapters)
        result['lora_gradients_verified'] = True
        torch.nn.utils.clip_grad_norm_(adapters.values(),1.0)
        optimizer.step()
        result['optimizer_success'] = True
        record('optimizer_complete')
        assert all(torch.isfinite(p).all() for p in adapters.values())
        assert any(not torch.equal(before[n],p.detach().cpu()) for n,p in adapters.items())
        assert frozen == w.frozen_hashes(model)
        result.update(base_frozen_hash_verified=True, lora_parameters_changed=True)
        model.save_pretrained(disposable)
        result['adapter_hashes'] = {str(f.relative_to(disposable)):r.digest(f) for f in disposable.rglob('*') if f.is_file()}
        del loss, inputs, optimizer, before, adapters, model, tokenizer, forward_kwargs
        gc.collect(); torch.cuda.empty_cache()
        record('unloaded_before_fresh_reload')
        fresh, tokenizer, _ = r.load(directory)
        reloaded = PeftModel.from_pretrained(fresh, disposable, is_trainable=False)
        reloaded.eval()
        with torch.no_grad():
            reload_loss = reloaded(**r.batch(turn)).loss
        assert torch.isfinite(reload_loss)
        result.update(fresh_base_adapter_reload='PASS', reload_loss=float(reload_loss.cpu()))
        del reload_loss, reloaded, fresh, tokenizer
        gc.collect(); torch.cuda.empty_cache()
        after_data = {name:r.digest(a.data/name) for name in files}
        assert before_data == after_data
        result.update(dataset_unchanged=True, status='PASS')
        r.save(a.output/'dataset-hashes-after.json', after_data)
        record('complete')
    except Exception as e:
        result.update(status='FAIL', error=repr(e), traceback=traceback.format_exc(),
                      OOM='out of memory' in str(e).lower())
        record('failed')
        raise
    finally:
        if disposable.exists():
            assert disposable.resolve().is_relative_to(a.output.resolve())
            shutil.rmtree(disposable)
        result['disposable_adapter_removed'] = True
        r.save(a.output/'result.json', result)


if __name__=='__main__':
    main()
