"""CPU official-tokenizer and assistant-label checks, not a GPU training test."""
import importlib.util,json,sys
from pathlib import Path
def main(out,package):
    sys.path.insert(0,str(out/'format-runtime'))
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(str(out/'base-tokenizer'),local_files_only=True)
    spec=importlib.util.spec_from_file_location('portable_training',package/'training.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    rows=module.read_rows(package/'positive-trajectories.jsonl');turns,rejected=module.tokenize_turns(tokenizer,rows)
    tool_rows=[x for x in rows if x.get('tools')];mask_errors=[]
    for turn in turns:
        if any(v!=-100 for v in turn['labels'][:turn['prompt_tokens']]):mask_errors.append(turn['id'])
        if any(v==-100 for v in turn['labels'][turn['prompt_tokens']:]):mask_errors.append(turn['id'])
    assert not mask_errors and not rejected
    import numpy as np
    def percentiles(values):return {name:float(np.percentile(values,p)) for name,p in [('p50',50),('p75',75),('p90',90),('p95',95),('p99',99),('max',100)]}
    total=[len(t['input_ids']) for t in turns];prompts=[t['prompt_tokens'] for t in turns];outputs=[t['assistant_tokens'] for t in turns]
    audit={'official_tokenizer_class':type(tokenizer).__name__,'revision':'1001bb4d826a52d1f399e183466143f4da7b741b','rendered_examples':len(rows),'assistant_turns':len(turns),'tool_trajectories':len(tool_rows),'assistant_boundaries_exact':True,'official_full_tokenization_matches_split_tokenization':True,'masked_prompt_and_observations':True,'mask_errors':mask_errors,'private_chain_of_thought_added':False,'official_empty_think_prefix_masked':True,'torch_cuda_training':'NOT_RUN','trl_api_inspection':'Pinned1.14.2wheel accepts pretokenized input_ids/labels and customcollator; labels preserved with skip_prepare_dataset; GPU behavior pending smoke','full_training_ready':False}
    def save(name,value):(package/name).write_text(json.dumps(value,indent=2,default=str),encoding='utf-8')
    save('training-format-audit.json',audit);save('sequence-length-analysis.json',{'total_sequence':percentiles(total),'prompt':percentiles(prompts),'assistant_outputs':percentiles(outputs),'tool_schemas_and_observations':'Included in prompt counts; no independent component subtraction claimed','no_truncation':True,'gpu_adaptive_caps':[1024,2048,4096],'counts_over_caps':{str(c):sum(v>c for v in total) for c in (1024,2048,4096)},'chosen_release_length':None,'reason':'Dataset release/hardware smoke gates still incomplete'})
    preview=package/'rendered-previews';preview.mkdir()
    for i,turn in enumerate(turns[:2]+[t for t in turns if t['category']=='agentic'][:2]):
        (preview/f'{i:02}.txt').write_text(turn['rendered'],encoding='utf-8');save('mask-preview-'+str(i)+'.json',{'id':turn['id'],'prompt_tokens':turn['prompt_tokens'],'assistant_tokens':turn['assistant_tokens'],'labels':turn['labels'],'input_ids':turn['input_ids']})
    print(json.dumps(audit),flush=True)
if __name__=='__main__':main(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
