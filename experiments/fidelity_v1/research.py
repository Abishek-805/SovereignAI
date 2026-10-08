"""Archive pinned upstream source as inert research data; install/import nothing."""
import base64,hashlib,json,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence/code-agent-fidelity-v1/reports/upstream'
REPOS={'nanobot':'HKUDS/nanobot','hermes':'NousResearch/hermes-agent','mini-swe':'SWE-agent/mini-swe-agent'}
def get(url):
    return urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'SovereignAI-source-audit'}),timeout=60).read()
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    for name,repo in REPOS.items():
        directory=OUT/name;directory.mkdir(exist_ok=True)
        if (directory/'manifest.json').exists():
            print('Preserved completed research '+name,flush=True);continue
        commit=json.loads(get('https://api.github.com/repos/'+repo+'/commits/HEAD'))
        saved=directory/'commit.json'
        if saved.exists():commit=json.loads(saved.read_text())
        else:saved.write_text(json.dumps(commit,indent=2),encoding='utf-8')
        sha=commit['sha'];tree=json.loads((directory/'tree.json').read_text()) if (directory/'tree.json').exists() else json.loads(get('https://api.github.com/repos/'+repo+'/git/trees/'+sha+'?recursive=1'))
        paths=[x['path'] for x in tree['tree'] if x['type']=='blob']
        if not (directory/'tree.json').exists():(directory/'tree.json').write_text(json.dumps(tree,indent=2),encoding='utf-8')
        preferred={'nanobot':['nanobot/agent/loop.py','nanobot/agent/context.py','nanobot/agent/tools/registry.py','nanobot/providers/base.py'],
                   'hermes':['run_agent.py','model_tools.py','tools/registry.py','agent/context_compressor.py'],
                   'mini-swe':['src/minisweagent/agents/default.py','src/minisweagent/environments/docker.py','src/minisweagent/models/openai.py']}[name]
        selected=[p for p in preferred if p in paths]
        entries=[]
        for path in selected:
            destination=directory/(path.replace('/','__')+'.txt')
            if destination.exists():raw=destination.read_bytes()
            else:
                try:raw=get('https://raw.githubusercontent.com/'+repo+'/'+sha+'/'+path)
                except urllib.error.HTTPError as exc:
                    if exc.code!=429:raise
                    blob=next(item for item in tree['tree'] if item['path']==path)['sha']
                    raw=base64.b64decode(json.loads(get('https://api.github.com/repos/'+repo+'/git/blobs/'+blob))['content'])
                destination.write_bytes(raw)
            entries.append({'path':path,'sha256':hashlib.sha256(raw).hexdigest(),'url':'https://github.com/'+repo+'/blob/'+sha+'/'+path,'bytes':len(raw)})
        manifest={'repository':repo,'commit':sha,'commit_date':commit['commit']['committer']['date'],'sources':entries,'purpose':'Inert source research only. Not installed, imported, or forked.'}
        (directory/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        print(json.dumps(manifest),flush=True)
        if name=='hermes':print('Additional context candidates: '+str([p for p in paths if p.endswith('.py') and any(s in p for s in ('compress','context','memory','tool_dispatch'))][:20]),flush=True)
if __name__=='__main__':main()
