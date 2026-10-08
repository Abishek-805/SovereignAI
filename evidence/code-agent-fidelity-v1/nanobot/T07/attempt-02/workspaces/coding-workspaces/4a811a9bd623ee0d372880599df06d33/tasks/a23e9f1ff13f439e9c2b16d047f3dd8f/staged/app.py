from flask import Flask,request,jsonify
app=Flask(__name__)
@app.get('/health')
def health():return jsonify(ok=True)
@app.post('/profile')
def profile():
    data=request.get_json()
    if not data or not data.get('display_name') or data.get('display_name').strip()=='':
        return jsonify(error='display_name required'),422
    return jsonify(display_name=data['display_name'].strip())
