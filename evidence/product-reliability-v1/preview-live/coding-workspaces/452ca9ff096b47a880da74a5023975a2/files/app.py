from flask import Flask,request,jsonify
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
