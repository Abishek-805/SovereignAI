import json,time
from pathlib import Path
from workflows.coding_workspace import CodingWorkspace
from workflows.web_preview import preview_request
from workflows.preview_session import close_sessions
from router.sandbox import CodeSandbox
root=Path('evidence/product-reliability-v1/preview-live');root.mkdir(parents=True,exist_ok=True)
coding=CodingWorkspace(root)
w=coding.create('Isolated preview acceptance')['workspace_id']
source='''from flask import Flask,request,jsonify
from flask_sqlalchemy import SQLAlchemy
app=Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI']='sqlite:///state.db'
db=SQLAlchemy(app)
class Item(db.Model):
 id=db.Column(db.Integer,primary_key=True)
 text=db.Column(db.String(100))
@app.get('/items')
def items():return jsonify([{'id':i.id,'text':i.text} for i in Item.query.all()])
@app.post('/items')
def add():
 item=Item(text=request.json['text']);db.session.add(item);db.session.commit()
 return jsonify(id=item.id,text=item.text)
@app.delete('/items/<int:id>')
def remove(id):
 item=db.session.get(Item,id);db.session.delete(item);db.session.commit();return '',204
'''
for name in ['app.py','other.py']:coding.write(w,name,source)
image=json.loads(Path('data/sandbox-validation.json').read_text())['image_id']
sandbox=CodeSandbox('docker',image)
results=[]
def call(target,method,path,body=None):
 start=time.monotonic();r=preview_request(coding,sandbox,root/'preview',w,target,path,method,body)
 results.append({'target':target,'method':method,'path':path,'response':r,'latency':time.monotonic()-start})
 (root/'results.json').write_text(json.dumps({'workspace':w,'results':results},indent=2))
 assert r['status']<400,r
 return json.loads(r['body']) if r['body'] else None
try:
 added=call('app.py','POST','/items',{'text':'acceptance'})
 assert call('app.py','GET','/items')==[added]
 assert call('other.py','GET','/items')==[]
 assert call('app.py','GET','/items')==[added]
 call('app.py','DELETE','/items/'+str(added['id']))
 assert call('app.py','GET','/items')==[]
 (root/'summary.json').write_text(json.dumps({'status':'PASS','checks':['CRUD','204','persistence after replacement','entrypoint isolation'],'latencies':[r['latency'] for r in results]},indent=2))
 print('PASS', [round(r['latency'],3) for r in results])
finally:close_sessions()
