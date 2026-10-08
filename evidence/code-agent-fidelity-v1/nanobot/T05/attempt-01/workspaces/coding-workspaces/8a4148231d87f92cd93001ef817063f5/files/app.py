from flask import Flask, request, jsonify
import json

app = Flask(__name__)

@app.get('/health')
def health():
    return jsonify(ok=True)

@app.post('/double')
def double():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify(error="Invalid JSON"), 422
    
    if data is None:
        return jsonify(error="Missing JSON body"), 422
    
    if not isinstance(data, dict):
        return jsonify(error="Request body must be a JSON object"), 422
    
    if 'value' not in data:
        return jsonify(error="Missing 'value' field"), 422
    
    value = data['value']
    
    if isinstance(value, bool):
        return jsonify(error="Value cannot be boolean"), 422
    
    if not isinstance(value, (int, float)):
        return jsonify(error="Value must be numeric"), 422
    
    result = value * 2
    return jsonify(result=result)
