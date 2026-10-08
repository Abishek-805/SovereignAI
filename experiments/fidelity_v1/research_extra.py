"""Follow execution delegation in the pinned source, never execute upstream."""
import base64,hashlib,json
from experiments.fidelity_v1.research import OUT,get
def main():
 for name,paths in {'nanobot':['nanobot/agent/runner.py'],'hermes':['agent/turn_facade.py','agent/tool_executor.py','agent/iteration_budget.py','agent/conversation_loop.py']}.items():
  folder=OUT/name;manifest=json.loads((folder/'manifest.json').read_text());tree=json.loads((folder/'tree.json').read_text());entries=[]
  for path in paths:
   item=next((i for i in tree['tree'] if i['path']==path),None)
   if item is None:continue
   dest=folder/(path.replace('/','__')+'.txt')
   if dest.exists():raw=dest.read_bytes()
   else:raw=base64.b64decode(json.loads(get('https://api.github.com/repos/'+manifest['repository']+'/git/blobs/'+item['sha']))['content']);dest.write_bytes(raw)
   entries.append({'path':path,'sha256':hashlib.sha256(raw).hexdigest(),'url':'https://github.com/'+manifest['repository']+'/blob/'+manifest['commit']+'/'+path,'bytes':len(raw)})
  (folder/'execution-sources-v2.json').write_text(json.dumps(entries,indent=2),encoding='utf-8');print(json.dumps(entries),flush=True)
if __name__=='__main__':main()
