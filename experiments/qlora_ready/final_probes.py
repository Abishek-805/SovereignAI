"""Bounded final probes. No full-training CLI or dataset-write operation exists."""
import argparse, collections, gc, hashlib, json, math, os, shutil, sys, time, traceback
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument('probe',choices=['stats','sparse','representative','high','dense','long0','long1','long2','accumulation','trainer','target26','target85','target113','target191','target243','real0','real1','real2'])
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--stats',type=Path,required=True)
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(a.data))
    import torch, worker as w
    from training_loss import SupervisedPositionTrainer,training_components,training_dataset
    from transformers import Trainer,TrainerCallback,AutoTokenizer
    r=w.r
    start=time.perf_counter()
    result={'probe':a.probe,'status':'RUNNING','RUN_TRAIN':False,'full_training':False,
            'model':r.MODEL,'revision':r.REVISION,'measurements':[],'microbatches':[]}
    disposable=a.output/'disposable-checkpoints'
    files=r.read(a.data/'package-manifest.json')['files']
    before_data={name:r.digest(a.data/name) for name in files}
    def save():
        r.save(a.output/'result.json',result)
    def record(stage):
        value=dict(stage=stage,elapsed_seconds=time.perf_counter()-start,memory=r.memory(),
                   cpu_rss_bytes=__import__('psutil').Process().memory_info().rss)
        free,capacity=torch.cuda.mem_get_info()
        value['device_memory']={'free_bytes':free,'capacity_bytes':capacity,'used_bytes':capacity-free,
                                'instantaneous_not_peak':True}
        result['measurements'].append(value)
        save();print(stage,json.dumps(value),flush=True)
        return value
    def quant(values):
        values=sorted(values)
        return {str(k):values[round((len(values)-1)*k/100)] for k in (0,50,90,95,99,100)}
    def targets(turn):
        return sum(x!=-100 for x in turn['labels'][1:])
    def equivalent():
        from transformers.loss.loss_utils import ForCausalLMLoss
        cases=[[2,3,4,5,6,7,8,9,10],[-100,-100,3,7,-100,2,-100,5,-100],
               [-100]*8+[3],[-100,4]+[-100]*7]
        values=[]
        for labels0 in cases:
            labels=torch.tensor([labels0])
            head=torch.nn.Linear(5,11)
            logits=head(torch.randn(1,9,5))
            shifted=torch.nn.functional.pad(labels,(0,1),value=-100)[:,1:]
            idx=torch.where(shifted[0]!=-100)[0]
            original=labels.clone()
            full=ForCausalLMLoss(logits,labels,11)
            reduced=ForCausalLMLoss(logits[:,idx],labels,11,shift_labels=shifted[:,idx])
            grad1=torch.autograd.grad(full,head.weight,retain_graph=True)[0]
            grad2=torch.autograd.grad(reduced,head.weight)[0]
            assert torch.allclose(full,reduced,atol=1e-6,rtol=1e-5)
            assert torch.allclose(grad1,grad2,atol=1e-6,rtol=1e-5)
            assert torch.equal(original,labels)
            values.append({'targets':idx.numel(),'loss':float(full.detach()),
                           'max_gradient_difference':float((grad1-grad2).abs().max())})
        return {'status':'PASS','atol':1e-6,'rtol':1e-5,'cases':values,
                'zero_targets':'rejected explicitly; no invented finite loss'}
    try:
        assert r.MODEL=='Qwen/Qwen3.5-4B-Base'
        assert r.REVISION=='1001bb4d826a52d1f399e183466143f4da7b741b'
        r.environment(a.output)
        directory=r.acquire(a.data,a.output)
        if a.probe=='stats':
            tokenizer=AutoTokenizer.from_pretrained(directory,local_files_only=True,trust_remote_code=False)
            turns=w.encoded_train(a.data,tokenizer,a.output)
            rows=[]
            for t in turns:
                n=len(t['input_ids']);count=targets(t)
                rows.append({'id':t['id'],'turn':t['turn'],'category':t['category'],'tokens':n,
                             'targets':count,'ignored':n-count,'density':count/n,
                             'at_least_4096':n>=4096,'within_95pct_4096':n>=.95*4096})
            grouped=collections.defaultdict(list)
            for row in rows:grouped[row['id']].append(row)
            assert len(grouped)==579
            records=[dict(id=k,assistant_turns=len(v),max_sequence_tokens=max(x['tokens'] for x in v),
                          max_supervised_targets=max(x['targets'] for x in v),
                          sum_supervised_targets=sum(x['targets'] for x in v),
                          max_density=max(x['density'] for x in v)) for k,v in grouped.items()]
            unique=sorted((max(v,key=lambda x:x['tokens']) for v in grouped.values()),key=lambda x:x['tokens'],reverse=True)
            counts=[x['targets'] for x in rows]
            stats={'status':'PASS','split':'train','record_count':579,'assistant_turn_count':len(rows),
                   'per_record':records,'per_assistant_turn':rows,'sequence_percentiles':quant([x['tokens'] for x in rows]),
                   'target_percentiles':quant(counts),'max_sequence_length':max(x['tokens'] for x in rows),
                   'max_density':max(x['density'] for x in rows),
                   'above_threshold':{str(n):sum(x>n for x in counts) for n in (100,500,1000,2000,3000)},
                   'target_histogram':{str(lo)+'-'+str(hi):sum(lo<=x<=hi for x in counts) for lo,hi in ((1,100),(101,500),(501,1000),(1001,2000),(2001,3000),(3001,4095))},
                   'highest_density_ids':[x['id'] for x in sorted(rows,key=lambda x:x['density'],reverse=True)[:10]],
                   'longest_unique':unique[:3],'dataset_unchanged':True,'no_source_text_or_oracle_answers_exported':True}
            r.save(a.output/'training-supervised-target-stats.json',stats)
            result.update(status='PASS',record_count=579,assistant_turn_count=len(rows),stats=stats['target_percentiles'])
            record('complete');return
        stats=r.read(a.stats)
        assert stats['status']=='PASS'
        model,tokenizer,loading=r.adapter_model(directory)
        model.train()
        turns=w.encoded_train(a.data,tokenizer,a.output)
        keyed={(t['id'],t['turn']):t for t in turns}
        original_keys={(t['id'],t['turn']):hashlib.sha256(json.dumps({k:t[k] for k in ('input_ids','attention_mask','labels')},sort_keys=True).encode()).hexdigest() for t in turns}
        frozen=w.frozen_hashes(model)
        adapters={n:q for n,q in model.named_parameters() if q.requires_grad}
        assert adapters and all('lora_' in n for n in adapters)
        before={n:q.detach().cpu().clone() for n,q in adapters.items()}
        result['load']=loading
        args,collate=training_components(tokenizer,disposable)
        args.eval_strategy='no';args.save_strategy='no';args.disable_tqdm=True
        args.dataloader_num_workers=0;args.max_steps=2
        args.logging_steps=1
        class TracedTrainer(SupervisedPositionTrainer):
            def compute_loss(self,model,inputs,return_outputs=False,num_items_in_batch=None):
                labels=inputs['labels']
                count=int((labels[:,1:]!=-100).sum())
                meta={'tokens':labels.shape[1],'targets':count,'num_items_in_batch':None if num_items_in_batch is None else int(num_items_in_batch),
                      'optimized_loss_used':True,'forward_success':False,'backward_success':False}
                result['current_microbatch']=meta
                loss=super().compute_loss(model,inputs,return_outputs,num_items_in_batch)
                scalar=loss[0] if return_outputs else loss
                assert torch.isfinite(scalar)
                meta.update(forward_success=True,loss=float(scalar.detach().cpu()))
                save()
                return loss
            def training_step(self,model,inputs,num_items_in_batch=None):
                t=time.perf_counter()
                value=super().training_step(model,inputs,num_items_in_batch)
                meta=dict(result['current_microbatch'])
                meta.update(backward_success=True,seconds=time.perf_counter()-t,memory=r.memory(),
                            cpu_rss_bytes=__import__('psutil').Process().memory_info().rss)
                result['microbatches'].append(meta);save()
                print('microbatch',len(result['microbatches']),json.dumps(meta),flush=True)
                return value
        def verify_gradients():
            assert any(q.grad is not None and q.grad.abs().sum()>0 for q in adapters.values())
            assert all(q.grad is None or torch.isfinite(q.grad).all() for q in adapters.values())
            assert all(q.grad is None for n,q in model.named_parameters() if n not in adapters)
        def representative():
            selected=[];seen=set()
            def add(t):
                key=(t['id'],t['turn'])
                if t['id'] not in seen:selected.append(t);seen.add(t['id'])
            for category in sorted({t['category'] for t in turns}):
                values=sorted((t for t in turns if t['category']==category),key=lambda t:len(t['input_ids']))
                add(values[len(values)//2])
            ordered=sorted(turns,key=lambda t:len(t['input_ids']))
            for i in range(16):
                add(ordered[round((len(ordered)-1)*i/15)])
                if len(selected)>=16:break
            for t in ordered:
                if len(selected)>=16:break
                add(t)
            assert len(selected)==16 and len({t['id'] for t in selected})==16
            return selected
        subset=representative()
        trainer=TracedTrainer(model=model,args=args,train_dataset=training_dataset(subset),data_collator=collate,processing_class=tokenizer)
        trainer.current_gradient_accumulation_steps=16
        result['trainer_loss_kwargs']=trainer.model_accepts_loss_kwargs
        result['loss_equivalence']=equivalent()
        trainer.create_optimizer()
        optimizer=trainer.optimizer
        torch.cuda.reset_peak_memory_stats()
        record('ready')
        if a.probe in ('sparse','representative','high','dense') or a.probe.startswith(('long','real','target')):
            if a.probe.startswith(('long','real')):
                if a.probe.startswith('real'):
                    ranked=sorted(stats['per_assistant_turn'],key=lambda t:(-t['targets'],-t['tokens'],t['id'],t['turn']))
                    assert ranked[0]['targets']==243
                    entry=ranked[int(a.probe[-1])]
                else:
                    entry=stats['longest_unique'][int(a.probe[-1])]
                turn=keyed[(entry['id'],entry['turn'])]
                inputs=r.batch(turn,length=4096)
                n=len(turn['input_ids'])
                assert inputs['input_ids'].shape[1]==4096
                for k in ('input_ids','attention_mask','labels'):
                    assert inputs[k][0,:n].detach().cpu().tolist()==turn[k]
                assert int((inputs['labels'][:,1:]!=-100).sum())==targets(turn)
                assert (inputs['labels'][0,n:]==-100).all()
                result.update(synthetic=False,source_id=turn['id'],source_turn=turn['turn'],
                              source_tokens=len(turn['input_ids']),source_target_count=targets(turn),
                              input_tokens=4096,truncated_count=0,unlabelled_padding_only=True)
            else:
                count=int(a.probe[6:]) if a.probe.startswith('target') else {'sparse':22,'representative':stats['target_percentiles']['50'],
                       'high':stats['target_percentiles']['99'],'dense':4095}[a.probe]
                assert 1<=count<=4095
                ordinary=tokenizer.encode('The value is a simple synthetic training example. ',add_special_tokens=False)
                ids=(ordinary*math.ceil(4096/len(ordinary)))[:4096]
                labels=[-100]*(4096-count)+ids[-count:]
                inputs={k:torch.tensor([v],device='cuda') for k,v in {'input_ids':ids,'attention_mask':[1]*4096,'labels':labels}.items()}
                result.update(synthetic=True,input_tokens=4096,supervised_targets=count,truncated_count=0)
            t=time.perf_counter()
            loss=trainer.compute_loss(model,inputs)
            record('forward_complete')
            loss.backward()
            result['backward_success']=True;record('backward_complete')
            verify_gradients()
            result.update(nonzero_lora_gradients=True,finite_lora_gradients=True,base_gradients_absent=True)
            torch.nn.utils.clip_grad_norm_(adapters.values(),1.0)
            optimizer.step();optimizer.zero_grad(set_to_none=True)
            result.update(optimizer_success=True,gradient_success=True,step_seconds=time.perf_counter()-t)
            record('optimizer_complete')
            del loss,inputs
        elif a.probe=='accumulation':
            selected=subset
            result['selection']=[{'id':t['id'],'turn':t['turn'],'category':t['category'],'tokens':len(t['input_ids']),'targets':targets(t)} for t in selected]
            total=sum(sum(x!=-100 for x in t['labels']) for t in selected)
            for turn in selected:
                value=trainer.training_step(model,collate([turn]),total if trainer.model_accepts_loss_kwargs else None)
                assert torch.isfinite(value);del value
            assert len(result['microbatches'])==16
            verify_gradients()
            torch.nn.utils.clip_grad_norm_(adapters.values(),1.0)
            optimizer.step();optimizer.zero_grad(set_to_none=True)
            assert all(q.grad is None for q in adapters.values())
            result.update(accumulation_success=True,optimizer_success=True,gradient_success=True)
            record('accumulation_optimizer_complete')
            repeated=min(subset,key=lambda t:len(t['input_ids']))
            growth=[]
            for i in range(4):
                value=trainer.training_step(model,collate([repeated]),sum(x!=-100 for x in repeated['labels']) if trainer.model_accepts_loss_kwargs else None)
                del value;verify_gradients()
                torch.nn.utils.clip_grad_norm_(adapters.values(),1.0)
                optimizer.step();optimizer.zero_grad(set_to_none=True)
                gc.collect()
                growth.append(record('repeated_optimizer_'+str(i)))
            allocations=[x['memory']['allocated'] for x in growth]
            monotonic=all(y>x+1024**2 for x,y in zip(allocations,allocations[1:]))
            material=allocations[-1]-allocations[0]>64*1024**2
            result['memory_growth']={'status':'MEMORY_GROWTH_DETECTED' if monotonic and material else 'PASS',
                                    'threshold_bytes':64*1024**2,'equivalent_steps':growth,
                                    'no_repeated_empty_cache':True,'bounded_check_not_full_run_proof':True}
            assert result['memory_growth']['status']=='PASS','MEMORY_GROWTH_DETECTED'
        else:
            # Two steps and one resumed step, each with the real accumulation=16. No epoch-sized run.
            selected=list(subset)
            selected.insert(0,keyed[(stats['longest_unique'][0]['id'],stats['longest_unique'][0]['turn'])])
            seen={t['id'] for t in selected}
            for t in sorted(turns,key=lambda t:len(t['input_ids'])):
                if len(selected)>=32:break
                if t['id'] not in seen:selected.append(t);seen.add(t['id'])
            assert len(selected)==32
            class CheckGrad(TrainerCallback):
                def on_pre_optimizer_step(self,args,state,control,**kwargs):
                    verify_gradients();result['gradient_success']=True
                def on_step_end(self,args,state,control,**kwargs):
                    assert all(q.grad is None for q in adapters.values())
                    result['optimizer_success']=True;record('trainer_optimizer_'+str(state.global_step))
                    if state.global_step==2 and not result.get('resuming_checkpoint'):
                        control.should_training_stop=True
            # Keep the scheduler horizon unchanged across the intentional checkpoint interruption.
            args.max_steps=3
            args.save_strategy='steps';args.save_steps=1;args.save_total_limit=2
            args.dataloader_pin_memory=False
            trainer=TracedTrainer(model=model,args=args,train_dataset=training_dataset(selected),data_collator=collate,processing_class=tokenizer,callbacks=[CheckGrad()])
            trainer.train()
            checkpoint=disposable/'checkpoint-2'
            assert checkpoint.is_dir()
            for file in ('trainer_state.json','optimizer.pt','scheduler.pt'):
                assert (checkpoint/file).is_file(),file
            result['checkpoint_hashes']={str(f.relative_to(checkpoint)):r.digest(f) for f in checkpoint.rglob('*') if f.is_file()}
            state=r.read(checkpoint/'trainer_state.json')
            assert state['global_step']==2
            assert any(t['tokens']>=stats['max_sequence_length'] for t in result['microbatches']), 'Longest example not visited; Trainer 4096 path unproven'
            saved={n:q.detach().cpu().clone() for n,q in adapters.items()}
            result['trainer_integration']='PASS';record('checkpoint_saved')
            assert frozen==w.frozen_hashes(model)
            del trainer,optimizer,model,adapters
            gc.collect();torch.cuda.empty_cache()
            from peft import PeftModel
            base,_,_=r.load(directory)
            base.config.use_cache=False
            from peft import prepare_model_for_kbit_training
            base=prepare_model_for_kbit_training(base,use_gradient_checkpointing=True)
            model=PeftModel.from_pretrained(base,checkpoint,is_trainable=True)
            adapters={n:q for n,q in model.named_parameters() if q.requires_grad}
            assert set(saved)==set(adapters)
            assert all(torch.equal(saved[n],q.detach().cpu()) for n,q in adapters.items())
            assert frozen==w.frozen_hashes(model)
            result['adapter_state_restored']=True
            args.max_steps=3
            resumed=TracedTrainer(model=model,args=args,train_dataset=training_dataset(selected),data_collator=collate,processing_class=tokenizer,callbacks=[CheckGrad()])
            original_load=resumed._load_optimizer_and_scheduler
            def checked_load(path):
                original_load(path)
                saved_opt=torch.load(Path(path)/'optimizer.pt',map_location='cpu',weights_only=True)
                actual=resumed.optimizer.state_dict()
                assert len(actual['state'])==len(saved_opt['state'])>0
                for key,v in saved_opt['state'].items():
                    for name,value in v.items():
                        current=actual['state'][key][name]
                        if torch.is_tensor(value):assert torch.equal(value,current.detach().cpu()),'Optimizer state mismatch'
                        else:assert current==value
                result['optimizer_state_restored']=True
            resumed._load_optimizer_and_scheduler=checked_load
            result['resuming_checkpoint']=True
            resumed.train(resume_from_checkpoint=str(checkpoint))
            assert resumed.state.global_step==3
            assert result.get('optimizer_state_restored')
            assert any(not torch.equal(saved[n],q.detach().cpu()) for n,q in adapters.items())
            result.update(checkpoint_resume='PASS',global_step_after_resume=3,adapter_changed_after_resume=True)
            record('checkpoint_resumed')
        assert all(torch.isfinite(q).all() for q in adapters.values())
        assert any(not torch.equal(before[n],q.detach().cpu()) for n,q in adapters.items())
        assert frozen==w.frozen_hashes(model)
        assert original_keys=={(t['id'],t['turn']):hashlib.sha256(json.dumps({k:t[k] for k in ('input_ids','attention_mask','labels')},sort_keys=True).encode()).hexdigest() for t in turns}
        result.update(status='PASS',base_hash_unchanged=True,adapter_parameters_changed=True,canonical_masks_unchanged=True)
        record('complete')
    except Exception as e:
        result.update(status='FAIL',error=repr(e),traceback=traceback.format_exc(),OOM='out of memory' in str(e).lower())
        try:record('failed')
        except Exception:save()
        raise
    finally:
        if disposable.exists():
            assert disposable.resolve().is_relative_to(a.output.resolve())
            shutil.rmtree(disposable)
        assert before_data=={name:r.digest(a.data/name) for name in files},'Dataset changed'
        result.update(dataset_unchanged=True,disposable_checkpoint_removed=True,elapsed_seconds=time.perf_counter()-start)
        save()

if __name__=='__main__':
    main()

