import ast,json,re,time,urllib.request
from scripts.full_qa_inventory import http,save,OUT
cases=[('recursion','Explain what recursion is in two sentences.'),('json','Return exactly JSON containing answer=42.'),('function','Write a Python function add(a,b). Return only code.'),('tool','Create a tool action to read main.py. Return JSON.'),('repair','Fix this deliberately broken Python function: def divide(a,b): return a / 0. It must return a/b and raise ValueError when b is zero.'),('offline','Do not use any external network. Explain what a local CPU does in one sentence.'),('summary','Summarize this supplied text in one sentence: The test laboratory contains seven repair bays and is supervised by Mira.')]
results=[]
for name,prompt in cases:
 r=http('/v1/chat/completions','POST',{'model':'sovereign-text','messages':[{'role':'user','content':prompt}],'max_tokens':256,'temperature':0,'stream':False,'chat_template_kwargs':{'enable_thinking':False}})
 answer=r.get('body',{}).get('choices',[{}])[0].get('message',{}).get('content','') if isinstance(r.get('body'),dict) else ''
 passed=r['status']==200 and bool(answer.strip())
 if name=='json':
  try:passed=passed and json.loads(answer)=={'answer':42}
  except Exception:passed=False
 if name=='function':
  try:
   tree=ast.parse(re.sub(r'^```(?:python)?\s*|\s*```$','',answer.strip()));passed=passed and any(isinstance(n,ast.FunctionDef) and n.name=='add' and [a.arg for a in n.args.args]==['a','b'] for n in tree.body)
  except Exception:passed=False
 if name=='summary':passed=passed and 'Mira' in answer and ('seven' in answer.lower() or '7' in answer)
 r.update(case=name,answer=answer,verdict='PASS' if passed else 'FAIL' if r['status'] else 'BLOCKED',oracle='Structural/content check; code behavior separately requires Docker')
 save('model/'+name+'.json',r);results.append(r);print(name,r['verdict'],round(r['latency'],2),flush=True)
# Streaming measured from actual received SSE, no inference from progress labels.
payload={'model':'sovereign-text','messages':[{'role':'user','content':'Explain recursion briefly.'}],'stream':True,'max_tokens':128,'temperature':0,'chat_template_kwargs':{'enable_thinking':False}}
start=time.monotonic();ttft=None;lines=[]
try:
 with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8088/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'}),timeout=180) as response:
  for line in response:
   lines.append(line.decode(errors='replace'))
   try:
    event=json.loads(line.decode()[6:]);text=event['choices'][0].get('delta',{}).get('content','')
    if text and ttft is None:ttft=time.monotonic()-start
   except Exception:pass
 save('model/stream.json',{'verdict':'PASS' if ttft is not None and any('[DONE]' in x for x in lines) else 'FAIL','ttft':ttft,'total_latency':time.monotonic()-start,'raw_stream':lines,'payload':payload})
except Exception as e:save('model/stream.json',{'verdict':'BLOCKED','error':str(e)})
save('model-audit.json',results)
