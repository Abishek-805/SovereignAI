"""Independent live UI-backend semantics and timing, generated code Docker only."""
import json,time
from pathlib import Path
from scripts.full_qa_inventory import http
out=Path('outputs/interaction-repair');out.mkdir(parents=True,exist_ok=True)
w=http('/coding/workspaces','POST',{'name':'Preview interaction diagnostic '+str(time.time_ns())})['body']['workspace_id']
source='''from flask import Flask,request,session,jsonify
app=Flask(__name__)
app.secret_key='preview-qa-key'
count=0
@app.get('/')
def home():return '<script src="/static/client.js"></script><button id="increment">Increment</button><div id="value">0</div>'
@app.post('/increment')
def increment():
 global count
 count+=1
 session['count']=session.get('count',0)+1
 return jsonify(count=count,cookie_count=session['count'])
@app.get('/empty')
def empty():return '',204
'''
for name,content in {'app.py':source,'static/client.js':"addEventListener('DOMContentLoaded',()=>document.getElementById('increment').addEventListener('click',async()=>{const r=await fetch('/increment',{method:'POST'});const data=await r.json();document.getElementById('value').textContent=data.count;}));"}.items():
 assert http('/coding/workspaces/'+w+'/files/'+name,'PUT',{'content':content})['status']==200
results=[]
for path,method in [('/','GET'),('/increment','POST'),('/increment','POST'),('/increment','POST'),('/empty','GET')]:
 r=http('/coding/workspaces/'+w+'/web-preview','POST',{'target':'app.py','path':path,'method':method})
 results.append(r);(out/'preview-live.json').write_text(json.dumps({'workspace_id':w,'results':results},indent=2),encoding='utf-8')
print(json.dumps({'workspace':w,'latencies':[r['latency'] for r in results],'responses':[r['body'] for r in results]}))
