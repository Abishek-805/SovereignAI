"""Portable Colab preparation/QLoRA smoke; full training requires explicit gates."""
import argparse,copy,hashlib,json,os,random,sys
from pathlib import Path
MODEL_NAME='Qwen/Qwen3.5-4B-Base'
MODEL_REVISION='1001bb4d826a52d1f399e183466143f4da7b741b'
def write(path,value):path.write_text(json.dumps(value,indent=2,default=str))
def read_rows(path):return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
def tokenize_turns(tokenizer,rows,max_length=None):
    output=[];rejected=[]
    for row in rows:
        if not row.get('quality',{}).get('verified'):raise ValueError('Unverified positive '+row['id'])
        messages=copy.deepcopy(row['messages']);tools=row.get('tools')
        # Native API stores arguments as JSON strings; official Base template
        # iterates mappings. Adapt representation only; canonical data stays raw.
        for message in messages:
            for call in message.get('tool_calls',[]):
                original=call['function'].get('arguments')
                if isinstance(original,str):
                    parsed=json.loads(original)
                    if not isinstance(parsed,dict):raise ValueError('Tool arguments must decode to object')
                    if json.loads(json.dumps(parsed,ensure_ascii=False))!=json.loads(original):raise ValueError('Argument representation changed values')
                    call['function']['arguments']=parsed
        for i,message in enumerate(messages):
            if message['role']!='assistant':continue
            kwargs={'tokenize':False,'enable_thinking':False}
            if tools:kwargs['tools']=tools
            prefix=tokenizer.apply_chat_template(messages[:i],add_generation_prompt=True,**kwargs)
            full=tokenizer.apply_chat_template(messages[:i+1],add_generation_prompt=False,**kwargs)
            if not full.startswith(prefix):raise ValueError('Assistant generation boundary mismatch '+row['id'])
            # Encode prefix/completion separately to enforce an exact assistant-only boundary.
            # Verify it reproduces the official full-sequence tokenization; otherwise stop.
            prefix_ids=tokenizer.encode(prefix,add_special_tokens=False);target_ids=tokenizer.encode(full[len(prefix):],add_special_tokens=False)
            ids=prefix_ids+target_ids
            if ids!=tokenizer.encode(full,add_special_tokens=False):raise ValueError('BPE boundary changed tokenization '+row['id'])
            if not target_ids:raise ValueError('Empty supervised response')
            if max_length and len(ids)>max_length:rejected.append({'id':row['id'],'turn':i,'tokens':len(ids),'reason':'OVERSIZE_NOT_TRUNCATED'});continue
            output.append({'id':row['id'],'category':row['category'],'turn':i,'input_ids':ids,'attention_mask':[1]*len(ids),'labels':[-100]*len(prefix_ids)+target_ids,'prompt_tokens':len(prefix_ids),'assistant_tokens':len(target_ids),'rendered':full})
    return output,rejected
def environment():
    import importlib.metadata as md
    import torch
    versions={p:md.version(p) if p in {d.metadata['Name'].lower() for d in md.distributions()} else None for p in ['torch','transformers','peft','trl','bitsandbytes','accelerate','datasets','unsloth']}
    if not torch.cuda.is_available():raise RuntimeError('CUDA GPU required; Colab Runtime > Change runtime type > GPU')
    props=torch.cuda.get_device_properties(0)
    return {'gpu':props.name,'vram_gib':props.total_memory/2**30,'cuda':torch.version.cuda,'libraries':versions,'bf16':torch.cuda.is_bf16_supported()}
def collate(batch,pad_token_id):
    import torch
    length=max(len(x['input_ids']) for x in batch)
    return {key:torch.tensor([x[key]+[(-100 if key=='labels' else 0 if key=='attention_mask' else pad_token_id)]*(length-len(x[key])) for x in batch]) for key in ['input_ids','attention_mask','labels']}
def load_worker(method,env,settings=None):
    settings=settings or {}
    import torch
    from transformers import AutoModelForImageTextToText,BitsAndBytesConfig
    from peft import LoraConfig,get_peft_model,prepare_model_for_kbit_training
    dtype=torch.bfloat16 if env['bf16'] else torch.float16
    params={'revision':MODEL_REVISION,'torch_dtype':dtype,'device_map':{'':0},'attn_implementation':'eager','trust_remote_code':False}
    if method=='qlora':params['quantization_config']=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=dtype)
    elif env['vram_gib']<24:raise RuntimeError('Standard LoRA fallback needs >=24GiB safety estimate; choose a larger GPU, not silent OOM retries')
    model=AutoModelForImageTextToText.from_pretrained(MODEL_NAME,**params)
    model.config.use_cache=False
    if method=='qlora':model=prepare_model_for_kbit_training(model,use_gradient_checkpointing=True)
    else:model.gradient_checkpointing_enable();model.enable_input_require_grads()
    config=LoraConfig(r=settings.get('LORA_R',16),lora_alpha=settings.get('LORA_ALPHA',32),lora_dropout=settings.get('LORA_DROPOUT',.05),target_modules='all-linear',exclude_modules=r'.*visual.*',task_type='CAUSAL_LM',bias='none')
    model=get_peft_model(model,config)
    for name,p in model.named_parameters():
        if 'visual' in name and p.requires_grad:raise RuntimeError('Unexpected trainable vision parameter '+name)
    model.print_trainable_parameters();return model
def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['preflight','smoke','train']);parser.add_argument('--dataset',type=Path,required=True);parser.add_argument('--output',type=Path,default=Path('/content/sovereignai-adapter'));parser.add_argument('--method',choices=['qlora','lora'],default='qlora');parser.add_argument('--runtime-config',type=Path);parser.add_argument('--approve-full-training',action='store_true');args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    settings=json.loads(args.runtime_config.read_text()) if args.runtime_config else {}
    import torch
    from transformers import AutoTokenizer,set_seed
    set_seed(42);random.seed(42);env=environment();write(args.output/'environment.json',env)
    tokenizer=AutoTokenizer.from_pretrained(MODEL_NAME,revision=MODEL_REVISION,trust_remote_code=False)
    if tokenizer.pad_token_id is None:tokenizer.pad_token=tokenizer.eos_token
    manifest=json.loads((args.dataset/'training_manifest.json').read_text())
    if manifest['base_revision']!=MODEL_REVISION:raise RuntimeError('Base revision mismatch')
    for name,digest in manifest['dataset_sha256'].items():
        if hashlib.sha256((args.dataset/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Dataset hash mismatch '+name)
    contamination=json.loads((args.dataset/'contamination-report.json').read_text())
    if contamination.get('status')!='AUTOMATED_SCREEN_CLEAR':raise RuntimeError('Contamination gate not clear')
    train=read_rows(args.dataset/'train.jsonl');validation=read_rows(args.dataset/'validation.jsonl')
    maximum=1024 if env['vram_gib']<20 else 2048 if env['vram_gib']<36 else 4096
    if settings.get('MAX_SEQ_LENGTH'):
        requested=int(settings['MAX_SEQ_LENGTH'])
        if not 128<=requested<=maximum:raise RuntimeError('Sequence override exceeds measured GPU safety cap or is too short')
        maximum=requested
    encoded,rejected=tokenize_turns(tokenizer,train,maximum);eval_rows,eval_rejected=tokenize_turns(tokenizer,validation,maximum)
    write(args.output/'sequence-screen.json',{'max_seq_length':maximum,'rejected':rejected+eval_rejected,'accepted_turns':len(encoded),'no_truncation':True})
    if not encoded or not eval_rows:raise RuntimeError('No complete train/validation sequences fit; use larger GPU or acquire shorter verified examples')
    if args.stage=='preflight':print('Preflight passed. GPU smoke not yet run.');return
    if args.stage=='train':
        if not args.approve_full_training:raise RuntimeError('Full training requires explicit approval flag')
        if not manifest.get('release_ready'):raise RuntimeError('Seed dataset is not release-ready; acquire more independently verified balanced families first')
        if rejected or eval_rejected:raise RuntimeError('Oversize rows excluded; cannot silently change approved training mixture')
        baseline=json.loads((args.dataset/'baseline-evaluation.json').read_text())
        if baseline.get('true_base_evaluated') is not True:raise RuntimeError('True Base evaluation required before training; instruct GGUF is not a substitute')
    model=None
    try:
        model=load_worker(args.method,env,settings)
        batch=collate([encoded[0]],tokenizer.pad_token_id);batch={k:v.to('cuda') for k,v in batch.items()}
        model.train();optimizer=torch.optim.AdamW((p for p in model.parameters() if p.requires_grad),lr=float(settings.get('LEARNING_RATE',1e-4)))
        loss=model(**batch).loss
        if not torch.isfinite(loss):raise RuntimeError('Non-finite smoke loss')
        loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);optimizer.step();optimizer.zero_grad(set_to_none=True)
        model.eval()
        with torch.no_grad():vloss=model(**{k:v.to('cuda') for k,v in collate([eval_rows[0]],tokenizer.pad_token_id).items()}).loss
        if not torch.isfinite(vloss):raise RuntimeError('Non-finite validation smoke loss')
        smoke=args.output/'smoke-adapter';model.save_pretrained(smoke);tokenizer.save_pretrained(smoke)
        # Reload into the unchanged in-memory base after unloading the smoke adapter.
        from peft import PeftModel
        base=model.unload();reloaded=PeftModel.from_pretrained(base,smoke,is_trainable=True);reloaded.eval()
        with torch.no_grad():reload_loss=reloaded(**batch).loss
        if not torch.isfinite(reload_loss):raise RuntimeError('Adapter reload forward failed')
        write(args.output/'training-method-decision.json',{'method':args.method,'smoke_passed':True,'train_loss':float(loss),'validation_loss':float(vloss),'reload_loss':float(reload_loss),'gpu':env,'full_training_started':False})
        if args.stage=='smoke':print('Smoke passed; separate artifact, not a trained product.');return
        # Reload original base/adapter initialization: never use the smoke-updated adapter for training.
        del reloaded,base,model,batch,optimizer;torch.cuda.empty_cache();model=load_worker(args.method,env,settings)
        from datasets import Dataset
        from trl import SFTConfig,SFTTrainer
        keys=['input_ids','attention_mask','labels']
        batch_size=int(settings.get('BATCH_SIZE',1))
        if batch_size<1 or batch_size>1 and env['vram_gib']<36:raise RuntimeError('Microbatch exceeds conservative measured GPU memory gate')
        trainer=SFTTrainer(model=model,processing_class=tokenizer,train_dataset=Dataset.from_list([{k:x[k] for k in keys} for x in encoded]),eval_dataset=Dataset.from_list([{k:x[k] for k in keys} for x in eval_rows]),data_collator=lambda b:collate(b,tokenizer.pad_token_id),args=SFTConfig(output_dir=str(args.output/'checkpoints'),num_train_epochs=float(settings.get('NUM_EPOCHS',2)),learning_rate=float(settings.get('LEARNING_RATE',1e-4)),per_device_train_batch_size=batch_size,per_device_eval_batch_size=1,gradient_accumulation_steps=int(settings.get('GRAD_ACCUMULATION',16)),gradient_checkpointing=True,bf16=env['bf16'],fp16=not env['bf16'],eval_strategy='epoch',save_strategy='epoch',logging_steps=5,report_to='none',packing=False,max_length=None,dataset_kwargs={'skip_prepare_dataset':True},load_best_model_at_end=False,optim='adamw_torch',loss_type='nll'))
        trainer.train();trainer.save_model(str(args.output/'last-adapter'));tokenizer.save_pretrained(args.output/'last-adapter')
        write(args.output/'selection-status.json',{'status':'VALIDATION_ORACLE_REVIEW_REQUIRED','selected_checkpoint':None,'training_loss_not_selection_metric':True,'no_deployment':True})
    except Exception as exc:
        write(args.output/'failure.json',{'stage':args.stage,'method':args.method,'error':repr(exc),'full_training_stopped':True,'fallback':'If NF4 unsupported (not OOM/format error), rerun smoke --method lora on >=24GiB GPU; never auto-switch method in same evidence run'})
        raise
if __name__=='__main__':main()
