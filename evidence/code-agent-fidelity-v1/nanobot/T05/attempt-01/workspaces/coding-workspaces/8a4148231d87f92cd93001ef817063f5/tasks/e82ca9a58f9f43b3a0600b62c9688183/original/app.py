from flask import Flask,request,jsonify
app=Flask(__name__)
@app.get('/health')
def health():return jsonify(ok=True)
@app.post('/double')
def double():return jsonify(result=0)
