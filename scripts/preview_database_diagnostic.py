import json,time
from pathlib import Path
from scripts.full_qa_inventory import http
out=Path('outputs/interaction-repair')
w=http('/coding/workspaces','POST',{'name':'Preview database isolation '+str(time.time_ns())})['body']['workspace_id']
source='''from flask import Flask,request,jsonify
from flask_sqlalchemy import SQLAlchemy
app=Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI']='sqlite:///preview.db'
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
for name in ['app.py','other.py']:assert http('/coding/workspaces/'+w+'/files/'+name,'PUT',{'content':source})['status']==200
results=[]
def call(target,method,path,body=None):
 r=http('/coding/workspaces/'+w+'/web-preview','POST',{'target':target,'method':method,'path':path,'body':body});results.append(r)
 (out/'preview-database.json').write_text(json.dumps({'workspace_id':w,'results':results},indent=2),encoding='utf-8')
 assert r['status']==200,r
 response=r['body'];assert response['status']<400,response
 return json.loads(response['body']) if response['body'] else None
added=call('app.py','POST','/items',{'text':'QA item'})
assert call('app.py','GET','/items')==[added]
assert call('other.py','GET','/items')==[]  # closes and saves app.py's session
assert call('app.py','GET','/items')==[added]
call('app.py','DELETE','/items/'+str(added['id']))
assert call('app.py','GET','/items')==[]
j=json.loads((out/'preview-database.json').read_text());j['status']='PASS';j['checks']=['CRUD','204 response','persistent SQLite after session replacement','entrypoint database isolation'];(out/'preview-database.json').write_text(json.dumps(j,indent=2),encoding='utf-8');print('PASS database CRUD, persistence and entrypoint isolation')
