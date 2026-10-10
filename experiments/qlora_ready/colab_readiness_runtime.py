"""Manual Colab stages. Generated project code is never executed here."""
import argparse, collections, gc, hashlib, importlib.metadata as md, json, platform, sys, time
from pathlib import Path

MODEL='Qwen/Qwen3.5-4B-Base'
REVISION='1001bb4d826a52d1f399e183466143f4da7b741b'
PINS={'torch':'2.11.0+cu130','transformers':'5.19.0','peft':'0.21.1','bitsandbytes':'0.50.2','accelerate':'1.15.0','datasets':'4.8.5'}

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()

def save(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False,default=str)+'\n',encoding='utf-8')
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def rows(path):return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]

def integrity(data):
    package=read(data/'package-manifest.json')
    assert all(digest(data/name)==value for name,value in package['files'].items()),'Package hash mismatch'
    for name,value in package['tokenizer_files'].items():assert digest(data/'base-tokenizer'/name)==value
    splits={s:rows(data/(s+'.adjusted.jsonl')) for s in ('train','validation','internal-test')}
    assert {s:len(v) for s,v in splits.items()}=={'train':579,'validation':65,'internal-test':66}
    assert len({r['id'] for v in splits.values() for r in v})==710
    sys.path.insert(0,str(data));from colab_format_helpers import scan
    families=collections.defaultdict(set)
    for s,values in splits.items():
        for row in values:
            assert row['quality']['verified'] and row['quality']['oracle']['passed']
            assert row['release_checks']['split_assigned']==s
            assert row['release_checks']['license_status'] in {'LICENSE_CONFIRMED','LICENSE_NOT_REQUIRED'}
            families[row['release_checks']['family_assigned']].add(s)
            if row['category']=='computation':assert not any(scan(m['content']) for m in row['messages'] if m['role'] in {'system','user'})
    assert all(len(v)==1 for v in families.values())
    return splits

def environment(out):
    import subprocess,torch,bitsandbytes,transformers,peft
    versions={p:md.version(p) for p in PINS}
    assert versions==PINS,('Exact runtime differs; do not silently substitute',versions)
    assert torch.cuda.is_available(),'CUDA unavailable'
    assert torch.version.cuda=='13.0','CUDA runtime mismatch'
    x=torch.ones(64,device='cuda');assert x.sum().item()==64;del x
    torch.cuda.synchronize();props=torch.cuda.get_device_properties(0)
    assert hasattr(bitsandbytes,'nn') and hasattr(transformers,'AutoModelForImageTextToText')
    probe=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,memory.used,driver_version','--format=csv,noheader'],capture_output=True,text=True)
    result={'status':'PASS','python':sys.version,'platform':platform.platform(),'libraries':versions,'cuda':torch.version.cuda,'gpu':props.name,'total_vram':props.total_memory,'bf16_supported':torch.cuda.is_bf16_supported(),'gpu_tensor_allocation':'PASS','quantization_import':'PASS','driver_probe':probe.stdout.strip(),'installed_record_hashes':{p:digest(Path(md.distribution(p).locate_file(next(f for f in md.distribution(p).files if str(f).endswith('.dist-info/RECORD'))))) for p in PINS},'not_a_full_training_fit_test':True}
    save(out/'colab-environment-report.json',result);return result

def acquire(data,out):
    from huggingface_hub import HfApi,snapshot_download
    info=HfApi().model_info(MODEL,revision=REVISION,files_metadata=True)
    assert info.sha==REVISION,'Resolved wrong Base revision'
    directory=Path(snapshot_download(MODEL,revision=REVISION,allow_patterns=['*.safetensors','*.safetensors.index.json','config.json','generation_config.json','tokenizer*','vocab.json','merges.txt','special_tokens_map.json','LICENSE']))
    config=read(directory/'config.json')
    assert config['model_type']=='qwen3_5' and config['architectures']==['Qwen3_5ForConditionalGeneration']
    assert digest(directory/'config.json')==digest(data/'base-tokenizer/config.json')
    hashes={}
    for name,value in read(data/'package-manifest.json')['tokenizer_files'].items():
        if name in {'config.json','tokenizer.json','tokenizer_config.json','vocab.json','merges.txt'}:assert digest(directory/name)==value
    for sibling in info.siblings:
        if not sibling.rfilename.endswith('.safetensors'):continue
        path=directory/sibling.rfilename;assert path.is_file()
        actual=digest(path);assert sibling.lfs and actual==sibling.lfs.sha256,'Safetensors digest mismatch'
        assert path.stat().st_size==sibling.lfs.size
        hashes[sibling.rfilename]=actual
    assert hashes,'No native weights'
    index=directory/'model.safetensors.index.json'
    if index.exists():assert set(read(index)['weight_map'].values())<=set(hashes)
    save(out/'base-model-identity.json',{'status':'PASS','model':MODEL,'revision':REVISION,'resolved_revision':info.sha,'architecture':config['architectures'],'config_sha256':digest(directory/'config.json'),'safetensors_sha256':hashes,'cache_path':str(directory),'instruct_or_GGUF_substitution':False})
    return directory

def memory():
    import torch,resource
    torch.cuda.synchronize()
    return {'allocated':torch.cuda.memory_allocated(),'reserved':torch.cuda.memory_reserved(),'peak_allocated':torch.cuda.max_memory_allocated(),'peak_reserved':torch.cuda.max_memory_reserved(),'cpu_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}

def load(directory):
    import torch
    from transformers import AutoModelForImageTextToText,AutoTokenizer,BitsAndBytesConfig,set_seed
    set_seed(42);torch.cuda.reset_peak_memory_stats()
    dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    started=time.perf_counter()
    model=AutoModelForImageTextToText.from_pretrained(directory,local_files_only=True,trust_remote_code=False,device_map={'':0},dtype=dtype,attn_implementation='eager',quantization_config=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=dtype))
    tokenizer=AutoTokenizer.from_pretrained(directory,local_files_only=True,trust_remote_code=False)
    if tokenizer.pad_token_id is None:tokenizer.pad_token=tokenizer.eos_token
    assert model.__class__.__name__=='Qwen3_5ForConditionalGeneration'
    return model,tokenizer,{'seconds':time.perf_counter()-started,'memory':memory(),'precision':str(dtype),'quantization':'NF4 double quant'}

def generate(model,tokenizer,messages,tools=None,limit=4096):
    import copy,torch
    messages=copy.deepcopy(messages)
    for m in messages:
        for c in m.get('tool_calls',[]):
            if isinstance(c['function']['arguments'],str):c['function']['arguments']=json.loads(c['function']['arguments'])
    kw={'tools':tools} if tools else {}
    text=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False,**kw)
    inputs=tokenizer(text,return_tensors='pt',add_special_tokens=False).to('cuda')
    started=time.perf_counter();torch.cuda.reset_peak_memory_stats()
    with torch.inference_mode():tokens=model.generate(**inputs,max_new_tokens=limit,do_sample=False,pad_token_id=tokenizer.pad_token_id)
    torch.cuda.synchronize()
    result={'raw_output':tokenizer.decode(tokens[0,inputs.input_ids.shape[-1]:],skip_special_tokens=False),'latency_seconds':time.perf_counter()-started,'memory':memory(),'prompt_tokens':inputs.input_ids.shape[-1],'generated_tokens':tokens.shape[-1]-inputs.input_ids.shape[-1]}
    del tokens,inputs;return result

def base_smoke(data,out):
    env=environment(out);directory=acquire(data,out);model,tokenizer,loading=load(directory);model.eval()
    prompts=['Name one common geometric shape.','What is 8 + 7?','Write a Python function that multiplies two numbers.','Reply with exactly one word: hello.']
    results=[{'prompt':p,**generate(model,tokenizer,[{'role':'user','content':p}],limit=128)} for p in prompts]
    assert all(r['generated_tokens']>0 and r['raw_output'] for r in results)
    save(out/'base-smoke-result.json',{'status':'PASS','model':MODEL,'revision':REVISION,'load':loading,'results':results,'runtime_only_not_quality_benchmark':True})
    del model,tokenizer;gc.collect();import torch;torch.cuda.empty_cache()
    save(out/'base-unload.json',{'status':'PASS','remaining_cuda_memory':memory(),'one_heavy_model_policy':True})

def baseline(data,out):
    environment(out);splits=integrity(data);directory=acquire(data,out);model,tokenizer,loading=load(directory);model.eval()
    results=[]
    for split in ('validation','internal-test'):
        for row in splits[split]:
            first=next(i for i,m in enumerate(row['messages']) if m['role']=='assistant')
            result={'id':row['id'],'split':split,'category':row['category'],'model':MODEL,'revision':REVISION,'adapter':None,'dataset_sha256':digest(data/(split+'.adjusted.jsonl')),'scope':'first assistant response only; agentic full rollout still required','code_executed':False,'independent_status':'NOT_TESTED',**generate(model,tokenizer,row['messages'][:first],row.get('tools'))}
            results.append(result);save(out/'base-predictions.json',results)
            print(split,row['id'],'captured; independent validation pending',flush=True)
    save(out/'baseline-capture-status.json',{'status':'BASELINE_BLOCKED','reason':'Prediction capture is not independent semantic/Docker validation; agentic rollout not executed','model':MODEL,'revision':REVISION,'load':loading,'captured':len(results),'true_base_weights_used':True,'fully_evaluated':False,'T01_T15_used':False})
    del model,tokenizer;gc.collect();import torch;torch.cuda.empty_cache()

def require_baseline(data,out):
    path=out/'independent-base-evaluation.json'
    assert path.is_file(),'BASELINE_BLOCKED: independently reviewed semantic/Docker/full-rollout evidence required'
    evidence=read(path);predictions=out/'base-predictions.json'
    assert evidence['model']==MODEL and evidence['revision']==REVISION and evidence['adapter'] is None
    assert evidence['prediction_sha256']==digest(predictions) and evidence['independently_verified'] is True
    splits=integrity(data);expected={(s,r['id']) for s in ('validation','internal-test') for r in splits[s]}
    assert len(evidence['results'])==131 and {(r['split'],r['id']) for r in evidence['results']}==expected
    categories={r['id']:r['category'] for s in ('validation','internal-test') for r in splits[s]}
    for row in evidence['results']:
        assert row['status'] in {'PASS','FAIL','UNKNOWN'} and row['independently_verified']
        artifact=(out/row['evidence_file']).resolve();assert artifact.is_relative_to(out.resolve()),'Evidence path outside output'
        assert row['evidence_sha256']==digest(artifact)
        assert row['category']==categories[row['id']]
        assert row['dataset_sha256']==digest(data/(row['split']+'.adjusted.jsonl'))
        if row['category'] in {'coding','agentic'}:assert row['docker_only_execution'] is True
        if row['category']=='agentic':assert row['full_stateful_rollout'] is True
    return evidence

def adapter_model(directory):
    from peft import LoraConfig,get_peft_model,prepare_model_for_kbit_training
    base,tokenizer,loading=load(directory);base.config.use_cache=False
    base=prepare_model_for_kbit_training(base,use_gradient_checkpointing=True)
    model=get_peft_model(base,LoraConfig(r=16,lora_alpha=32,lora_dropout=.05,target_modules='all-linear',exclude_modules=r'.*visual.*',task_type='CAUSAL_LM',bias='none'))
    assert all(not p.requires_grad for n,p in model.named_parameters() if 'lora_' not in n)
    assert all(not p.requires_grad for n,p in model.named_parameters() if 'visual' in n)
    return model,tokenizer,loading

def batch(turn,device='cuda',length=None):
    import torch
    values={k:list(turn[k]) for k in ('input_ids','attention_mask','labels')}
    if length:
        assert length>=len(values['input_ids'])
        extra=length-len(values['input_ids']);values['input_ids'] += [values['input_ids'][-1]]*extra;values['attention_mask'] += [1]*extra;values['labels'] += [-100]*extra
    return {k:torch.tensor([v],device=device) for k,v in values.items()}

def qlora_smoke(data,out):
    import torch
    environment(out);require_baseline(data,out);assert read(out/'base-smoke-result.json')['status']=='PASS'
    from colab_format_helpers import tokenize_turns
    directory=acquire(data,out);model,tokenizer,loading=adapter_model(directory)
    train=integrity(data)['train'];encoded,rejected=tokenize_turns(tokenizer,train,4096);assert not rejected
    small=min(encoded,key=lambda r:len(r['input_ids']));model.train()
    adapters={n:p for n,p in model.named_parameters() if p.requires_grad};assert adapters
    before={n:p.detach().cpu().clone() for n,p in adapters.items()}
    optimizer=torch.optim.AdamW(adapters.values(),lr=1e-4)
    torch.cuda.reset_peak_memory_stats();started=time.perf_counter();inputs=batch(small)
    loss=model(**inputs).loss;assert torch.isfinite(loss)
    forward_memory=memory();loss.backward();backward_memory=memory()
    assert any(p.grad is not None and torch.isfinite(p.grad).all() and p.grad.abs().sum()>0 for p in adapters.values())
    assert all(p.grad is None or torch.isfinite(p.grad).all() for p in adapters.values())
    assert all(p.grad is None for n,p in model.named_parameters() if 'lora_' not in n)
    torch.nn.utils.clip_grad_norm_(adapters.values(),1.0);optimizer.step();optimizer.zero_grad(set_to_none=True)
    assert any(not torch.equal(before[n],p.detach().cpu()) for n,p in adapters.items())
    step={'loss':float(loss.detach().cpu()),'seconds':time.perf_counter()-started,'forward_memory':forward_memory,'backward_memory':backward_memory,'optimizer_memory':memory(),'source_train_id':small['id'],'base_frozen':True,'adapter_gradients_verified':True,'adapter_parameters_changed':True}
    smoke=out/'temporary-smoke-adapter';assert not smoke.exists(),'Do not overwrite a prior smoke adapter'
    model.save_pretrained(smoke);tokenizer.save_pretrained(smoke)
    # Full unload: do not reuse an in-memory Base or smoke-updated adapter for training.
    del loss,inputs,optimizer,before,adapters,model,tokenizer;gc.collect();torch.cuda.empty_cache();unloaded=memory()
    from peft import PeftModel
    fresh,tokenizer,_=load(directory);reloaded=PeftModel.from_pretrained(fresh,smoke,is_trainable=False);reloaded.eval()
    with torch.no_grad():reload_loss=reloaded(**batch(small)).loss
    assert torch.isfinite(reload_loss)
    reload_value=float(reload_loss.cpu());del reload_loss,reloaded,fresh,tokenizer;gc.collect();torch.cuda.empty_cache()
    save(out/'qlora-smoke-result.json',{'status':'PASS','model':MODEL,'revision':REVISION,'load':loading,'step':step,'fully_unloaded_before_reload':True,'unloaded_memory':unloaded,'reload_loss':reload_value,'adapter_reload':'PASS','full_training_run':False})

def fit(data,out):
    import torch
    environment(out);assert read(out/'qlora-smoke-result.json')['status']=='PASS'
    from colab_format_helpers import tokenize_turns
    directory=acquire(data,out);model,tokenizer,loading=adapter_model(directory)
    encoded,rejected=tokenize_turns(tokenizer,integrity(data)['train'],4096);assert not rejected
    turn=max(encoded,key=lambda r:len(r['input_ids']));inputs=batch(turn,length=4096)
    model.train();torch.cuda.reset_peak_memory_stats();started=time.perf_counter()
    loss=model(**inputs).loss;assert torch.isfinite(loss);forward=memory();loss.backward();backward=memory()
    optimizer=torch.optim.AdamW((p for p in model.parameters() if p.requires_grad),lr=1e-4);optimizer.step()
    result={'status':'PASS','candidate_length':4096,'actual_training_turn_tokens':len(turn['input_ids']),'synthetic_padding_for_fit_probe_only':True,'canonical_dataset_modified':False,'load':loading,'forward':forward,'backward':backward,'optimizer':memory(),'seconds':time.perf_counter()-started,'loss':float(loss.detach().cpu()),'fit_adapter_discarded_not_used_for_training':True}
    del loss,inputs,optimizer,model,tokenizer;gc.collect();torch.cuda.empty_cache();save(out/'sequence-fit-result.json',result)

def training_guard(data,out,run_train):
    assert run_train is True,'Full training disabled: RUN_TRAIN=False'
    integrity(data);require_baseline(data,out)
    for name in ('colab-environment-report.json','base-model-identity.json','base-smoke-result.json','qlora-smoke-result.json','sequence-fit-result.json'):assert read(out/name)['status']=='PASS',name
    assert read(out/'sequence-fit-result.json')['candidate_length']==4096

def train(data,out,run_train=False):
    training_guard(data,out,run_train)
    environment(out)
    import torch
    from training_loss import SupervisedPositionTrainer,training_components,training_dataset
    from colab_format_helpers import tokenize_turns
    directory=acquire(data,out);model,tokenizer,_=adapter_model(directory)
    splits=integrity(data);encoded,oversize=tokenize_turns(tokenizer,splits['train'],4096);validation,rejected=tokenize_turns(tokenizer,splits['validation'],4096)
    assert not oversize and not rejected
    checkpoint=out/'training-checkpoints';assert not checkpoint.exists(),'Never overwrite an earlier training run'
    args,collate=training_components(tokenizer,checkpoint)
    trainer=SupervisedPositionTrainer(model=model,args=args,train_dataset=training_dataset(encoded),eval_dataset=training_dataset(validation),data_collator=collate,processing_class=tokenizer)
    trainer.train();trainer.save_model(str(out/'last-adapter'));tokenizer.save_pretrained(out/'last-adapter')
    save(out/'checkpoint-selection-status.json',{'status':'VALIDATION_ORACLE_REVIEW_REQUIRED','selected_checkpoint':None,'loss_not_selection_metric':True,'internal_test_used_for_selection':False,'production_export':False})

def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['integrity','environment','acquire','base-smoke','baseline','qlora-smoke','fit','train']);p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--run-train',action='store_true');args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    try:
        if args.stage=='integrity':integrity(args.data);print('Dataset integrity PASS')
        elif args.stage=='environment':environment(args.output)
        elif args.stage=='acquire':environment(args.output);acquire(args.data,args.output)
        elif args.stage=='train':train(args.data,args.output,args.run_train)
        else:{'base-smoke':base_smoke,'baseline':baseline,'qlora-smoke':qlora_smoke,'fit':fit}[args.stage](args.data,args.output)
    except Exception as exc:
        save(args.output/(args.stage+'-failure.json'),{'status':'TRAINING_BLOCKED','stage':args.stage,'error':repr(exc),'no_automatic_method_or_version_fallback':True});raise

if __name__=='__main__':main()
