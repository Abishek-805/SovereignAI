import hashlib,json,os,time
from pathlib import Path
import httpx
root=Path(__file__).resolve().parents[1]
items=[('Qwen/Qwen2.5-Coder-3B-Instruct-GGUF','f74adce6aa16316c625447af059dbebe4983757c','qwen2.5-coder-3b-instruct-q4_k_m.gguf',2104932800,'724fb256bec1ff062b2f65e4569e871ad2e95ab2a3989723d1769c54294730b7'),('unsloth/Qwen3.5-4B-GGUF','e87f176479d0855a907a41277aca2f8ee7a09523','Qwen3.5-4B-Q4_K_M.gguf',2740937888,'00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4'),('unsloth/gemma-4-E2B-it-GGUF','0314792d7f1f7e229411f620751375812bb9faf2','gemma-4-E2B-it-Q4_K_M.gguf',3106738272,'740185b21d22ceb83a11c3aa62ad5842ef32c70f6096d756bbee85a1e4ec34b8')]
for repo,revision,name,size,expected in items:
 target=root/'models'/name
 if target.is_file() and target.stat().st_size==size:
  with target.open('rb') as existing:
   if hashlib.file_digest(existing,'sha256').hexdigest()==expected:
    print('Verified existing',name,flush=True);continue
 temp=target.with_suffix('.gguf.download');digest=hashlib.sha256();count=0;next_report=256*1024**2
 with httpx.stream('GET',f'https://huggingface.co/{repo}/resolve/{revision}/{name}',follow_redirects=True,timeout=httpx.Timeout(180,connect=30)) as response:
  response.raise_for_status()
  with temp.open('wb') as out:
   for chunk in response.iter_bytes(1024*1024):
    out.write(chunk);digest.update(chunk);count+=len(chunk)
    if count>=next_report:print(name,round(count/size*100,1),'%',flush=True);next_report+=256*1024**2
 if count!=size or digest.hexdigest()!=expected:raise RuntimeError('Model integrity mismatch: '+name)
 os.replace(temp,target);print('Verified',name,flush=True)
(root/'benchmarks/model-candidate-assets.json').write_text(json.dumps([dict(repository=r,revision=v,file=n,size=s,sha256=h) for r,v,n,s,h in items],indent=2))
