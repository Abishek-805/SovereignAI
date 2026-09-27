import json,time,urllib.request,subprocess,psutil
from pathlib import Path
base='http://127.0.0.1:8088'
def post(path,body):
 r=urllib.request.Request(base+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 return json.load(urllib.request.urlopen(r,timeout=120))
def snap():
 processes=[]
 for p in psutil.process_iter(['name','memory_info']):
  if p.info['name']=='llama-server.exe':processes.append({'pid':p.pid,'rss_mib':round(p.info['memory_info'].rss/2**20,1)})
 gpu=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True).strip()
 return {'model_processes':processes,'gpu_total_used_mib':int(gpu),'available_system_ram_mib':round(psutil.virtual_memory().available/2**20)}
evidence={'before':snap(),'unload':post('/workbench/model/unload',{})};evidence['unloaded']=snap()
r=post('/v1/chat/completions',{'model':'sovereign-text','messages':[{'role':'user','content':'Reply with OK.'}],'max_tokens':8,'stream':False})
evidence['reload_reply']=r['choices'][0]['message']['content'];evidence['loaded']=snap()
time.sleep(65);evidence['idle_65_seconds']=snap();evidence['final_unload']=post('/workbench/model/unload',{});evidence['stopped']=snap()
Path('benchmarks/ux-memory-cycle.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8');print(json.dumps(evidence,indent=2))
