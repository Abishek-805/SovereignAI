"""New independent property fixtures; no historical task imports or model code."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'evidence/code-agent-fidelity-v1'
def suite(body):return 'import unittest,json,subprocess,sys\nfrom pathlib import Path\n'+body+'\n'
def cases():
 c=[]
 def add(id,category,request,starting,positive,tests,mode='accept'):
  files={**starting,'keep.txt':'unrelated valuable data\n','test_acceptance.py':suite(tests)}
  c.append({'task_id':id,'category':category,'request':request,'files':files,'positive_changes':positive,'mode':mode})
 add('T01','single_file_rename','Rename greet to welcome in names.py. Preserve its output and all unrelated files.',
 {'names.py':'def greet(name):\n    return "Hello " + name\n'},
 {'names.py':'def welcome(name):\n    return "Hello " + name\n'},
 '''import names
class Check(unittest.TestCase):
 def test_new_symbol(self):self.assertEqual(names.welcome('Ada'),'Hello Ada')
 def test_old_symbol_removed(self):self.assertFalse(hasattr(names,'greet'))
 def test_other_input(self):self.assertEqual(names.welcome('Lin'),'Hello Lin')''')
 add('T02','multi_file_rename','Rename read_number to load_number across numbers_io.py and caller.py. Update imports/calls, preserve behavior and unrelated files.',
 {'numbers_io.py':'def read_number():\n    return 23\n','caller.py':'from numbers_io import read_number\nprint(read_number())\n'},
 {'numbers_io.py':'def load_number():\n    return 23\n','caller.py':'from numbers_io import load_number\nprint(load_number())\n'},
 '''import numbers_io
class Check(unittest.TestCase):
 def test_new_symbol(self):self.assertEqual(numbers_io.load_number(),23)
 def test_old_removed(self):self.assertFalse(hasattr(numbers_io,'read_number'))
 def test_caller(self):self.assertEqual(subprocess.check_output([sys.executable,'caller.py'],text=True).strip(),'23')''')
 add('T03','bug_fix','Fix stats.py mean: use the correct denominator and raise ValueError for an empty sequence. Preserve tag().',
 {'stats.py':'def mean(values):\n    return sum(values)/(len(values)+1)\ndef tag():\n    return "stable"\n'},
 {'stats.py':'def mean(values):\n    if not values:raise ValueError("empty")\n    return sum(values)/len(values)\ndef tag():\n    return "stable"\n'},
 '''import stats
class Check(unittest.TestCase):
 def test_mean(self):self.assertEqual(stats.mean([2,4,9]),5)
 def test_single(self):self.assertEqual(stats.mean([8]),8)
 def test_empty(self):
  with self.assertRaises(ValueError):stats.mean([])
 def test_preserved(self):self.assertEqual(stats.tag(),'stable')''')
 add('T04','function_addition','Add clamp(value, low, high) to math_ops.py. Return the nearest bound when outside the range; reject low > high with ValueError. Preserve multiply.',
 {'math_ops.py':'def multiply(a,b):\n    return a*b\n'},
 {'math_ops.py':'def multiply(a,b):\n    return a*b\ndef clamp(value,low,high):\n    if low>high:raise ValueError("bounds")\n    return min(high,max(low,value))\n'},
 '''import math_ops
class Check(unittest.TestCase):
 def test_low(self):self.assertEqual(math_ops.clamp(-7,0,8),0)
 def test_high(self):self.assertEqual(math_ops.clamp(12,0,8),8)
 def test_inside(self):self.assertEqual(math_ops.clamp(3,0,8),3)
 def test_invalid(self):
  with self.assertRaises(ValueError):math_ops.clamp(1,5,2)
 def test_preserved(self):self.assertEqual(math_ops.multiply(6,7),42)''')
 app='''from flask import Flask,request,jsonify
app=Flask(__name__)
@app.get('/health')
def health():return jsonify(ok=True)
@app.post('/double')
def double():return jsonify(result=0)
'''
 good='''from flask import Flask,request,jsonify
app=Flask(__name__)
@app.get('/health')
def health():return jsonify(ok=True)
@app.post('/double')
def double():
 data=request.get_json(silent=True)
 value=data.get('value') if isinstance(data,dict) else None
 if isinstance(value,bool) or not isinstance(value,(int,float)):return jsonify(error='numeric value required'),422
 return jsonify(result=value*2)
'''
 add('T05','api_interface','Implement POST /double in app.py: JSON object with numeric value -> JSON result equal to twice the value. Reject malformed, missing, boolean or non-numeric values with JSON HTTP 422. Preserve GET /health.',{'app.py':app},{'app.py':good},
 '''from app import app
class Check(unittest.TestCase):
 def test_numeric(self):self.assertEqual(app.test_client().post('/double',json={'value':3.5}).get_json(),{'result':7.0})
 def test_negative(self):self.assertEqual(app.test_client().post('/double',json={'value':-2}).get_json(),{'result':-4})
 def test_invalid(self):
  for body in ({},{'value':True},{'value':'bad'},[]):
   r=app.test_client().post('/double',json=body);self.assertEqual(r.status_code,422);self.assertTrue(r.is_json)
 def test_malformed(self):
  r=app.test_client().post('/double',data='{broken',content_type='application/json');self.assertEqual(r.status_code,422);self.assertTrue(r.is_json)
 def test_preserved(self):self.assertEqual(app.test_client().get('/health').get_json(),{'ok':True})''')
 add('T06','multi_file_feature','Implement events.py counts(events) counting event kind values; missing/non-string kind raises ValueError. Implement report.py render(events) using counts to produce sorted kind:count lines. Preserve version().',
 {'events.py':'def counts(events):\n    return {}\ndef version():\n    return "v1"\n','report.py':'def render(events):\n    return ""\n'},
 {'events.py':'def counts(events):\n    result={}\n    for e in events:\n        if not isinstance(e,dict) or not isinstance(e.get("kind"),str):raise ValueError("kind")\n        result[e["kind"]]=result.get(e["kind"],0)+1\n    return result\ndef version():\n    return "v1"\n','report.py':'from events import counts\ndef render(events):\n    return "\\n".join(f"{k}:{v}" for k,v in sorted(counts(events).items()))\n'},
 '''import events,report
class Check(unittest.TestCase):
 def test_count(self):self.assertEqual(events.counts([{'kind':'b'},{'kind':'a'},{'kind':'b'}]),{'a':1,'b':2})
 def test_render(self):self.assertEqual(report.render([{'kind':'b'},{'kind':'a'},{'kind':'b'}]),'a:1\\nb:2')
 def test_invalid(self):
  with self.assertRaises(ValueError):events.counts([{}])
 def test_preserved(self):self.assertEqual(events.version(),'v1')''')
 add('T07','ui_backend','Coordinate profile UI/backend change: ui.js buildPayload(name) emits trimmed display_name; form.html must use input name display_name. app.py POST /profile accepts display_name, returns it as JSON; blank input gets JSON 422. Retain CommonJS export for testing and preserve /health.',
 {'ui.js':'function buildPayload(name){return {nickname:name};}\nmodule.exports={buildPayload};\n','form.html':'<form><input name="nickname"></form>\n','app.py':app.replace("'/double'","'/profile'")},
 {'ui.js':'function buildPayload(name){return {display_name:name.trim()};}\nmodule.exports={buildPayload};\n','form.html':'<form><input name="display_name"></form>\n','app.py':good.replace("'/double'","'/profile'").replace("value=data.get('value') if isinstance(data,dict) else None","value=data.get('display_name') if isinstance(data,dict) else None").replace("if isinstance(value,bool) or not isinstance(value,(int,float)):","if not isinstance(value,str) or not value.strip():").replace('return jsonify(result=value*2)','return jsonify(display_name=value.strip())')},
 '''from app import app
class Check(unittest.TestCase):
 def test_wire(self):
  payload=json.loads(subprocess.check_output(['node','-e',"console.log(JSON.stringify(require('./ui.js').buildPayload('  Ada  ')))"],text=True))
  self.assertEqual(payload,{'display_name':'Ada'});self.assertEqual(app.test_client().post('/profile',json=payload).get_json(),payload)
 def test_form(self):self.assertIn('name="display_name"',Path('form.html').read_text())
 def test_invalid(self):
  r=app.test_client().post('/profile',json={'display_name':' '});self.assertEqual(r.status_code,422);self.assertTrue(r.is_json)
 def test_preserved(self):self.assertEqual(app.test_client().get('/health').get_json(),{'ok':True})''')
 add('T08','state_identity','Fix inventory.py set_quantity(item_id, quantity). Integer IDs and their decimal-string form refer to the same existing integer-key item. Reject boolean IDs and negative/non-integer quantities with ValueError; unknown IDs raise KeyError. Never create duplicate string-key items. Preserve label().',
 {'inventory.py':'items={42:{"quantity":2}}\ndef set_quantity(item_id,quantity):\n    items[item_id]={"quantity":quantity}\ndef label():\n    return "warehouse"\n'},
 {'inventory.py':'items={42:{"quantity":2}}\ndef set_quantity(item_id,quantity):\n    if isinstance(item_id,bool) or not isinstance(quantity,int) or isinstance(quantity,bool) or quantity<0:raise ValueError("invalid")\n    try:key=int(item_id)\n    except (TypeError,ValueError):raise ValueError("id")\n    if key not in items:raise KeyError(key)\n    items[key]["quantity"]=quantity\ndef label():\n    return "warehouse"\n'},
 '''import inventory
class Check(unittest.TestCase):
 def setUp(self):inventory.items.clear();inventory.items[42]={'quantity':2}
 def test_string_id(self):inventory.set_quantity('42',9);self.assertEqual(inventory.items,{42:{'quantity':9}})
 def test_integer_id(self):inventory.set_quantity(42,7);self.assertEqual(inventory.items[42]['quantity'],7)
 def test_invalid(self):
  for ident,quantity in ((True,2),(42,-1),(42,False),(42,1.5)):
   with self.assertRaises(ValueError):inventory.set_quantity(ident,quantity)
 def test_unknown(self):
  with self.assertRaises(KeyError):inventory.set_quantity('99',2)
  self.assertNotIn(99,inventory.items)
 def test_preserved(self):self.assertEqual(inventory.label(),'warehouse')''')
 add('T09','test_failure_repair','Repair errors.py divide: return the quotient normally, and RAISE ValueError for zero denominator, never return an exception object. Preserve identity(). Run the supplied tests and use actual failures.',
 {'errors.py':'def divide(a,b):\n    if b==0:return ValueError("zero")\n    return a/b\ndef identity():\n    return "keep"\n'},
 {'errors.py':'def divide(a,b):\n    if b==0:raise ValueError("zero")\n    return a/b\ndef identity():\n    return "keep"\n'},
 '''import errors
class Check(unittest.TestCase):
 def test_normal(self):self.assertEqual(errors.divide(15,3),5)
 def test_exception(self):
  with self.assertRaises(ValueError):errors.divide(1,0)
 def test_preserved(self):self.assertEqual(errors.identity(),'keep')''')
 starting={'store.py':'reservations={}\ndef reset():\n    reservations.clear()\n','service.py':'def reserve(name,seats,capacity):\n    return {}\ndef cancel(token):\n    return False\n','summary.py':'def summary():\n    return {}\n'}
 positive={'service.py':'''import store
def reserve(name,seats,capacity):
 if not isinstance(name,str) or not name.strip() or isinstance(seats,bool) or not isinstance(seats,int) or seats<=0:raise ValueError('request')
 if sum(r['seats'] for r in store.reservations.values())+seats>capacity:raise ValueError('capacity')
 token=max(store.reservations,default=0)+1
 store.reservations[token]={'name':name,'seats':seats}
 return token
def cancel(token):
 if token not in store.reservations:raise KeyError(token)
 return store.reservations.pop(token)
''','summary.py':'''import store
def summary():return {'count':len(store.reservations),'seats':sum(r['seats'] for r in store.reservations.values())}
'''}
 add('T10','complex_dependent_edits','Implement reservation feature across store.py, service.py, summary.py. reserve(name,seats,capacity) stores a reservation and returns an integer token. Reject blank names, boolean/non-integer/nonpositive seats and capacity overflow with ValueError and no state mutation. cancel(token) removes it; unknown token raises KeyError. summary() returns count and seats from shared store. Preserve reset().',starting,positive,
 '''import store,service,summary
class Check(unittest.TestCase):
 def setUp(self):store.reset()
 def test_shared_state(self):
  a=service.reserve('Ada',2,6);b=service.reserve('Lin',3,6);self.assertIsInstance(a,int);self.assertNotEqual(a,b);self.assertEqual(summary.summary(),{'count':2,'seats':5});self.assertIn(a,store.reservations)
 def test_overflow_atomic(self):
  service.reserve('Ada',4,5);before=dict(store.reservations)
  with self.assertRaises(ValueError):service.reserve('Lin',2,5)
  self.assertEqual(store.reservations,before)
 def test_invalid_atomic(self):
  for name,seats in (('',1),('A',0),('A',-1),('A',True),('A',1.5)):
   with self.assertRaises(ValueError):service.reserve(name,seats,5)
  self.assertEqual(store.reservations,{})
 def test_cancel(self):
  token=service.reserve('Ada',2,5);service.cancel(token);self.assertEqual(summary.summary(),{'count':0,'seats':0})
  with self.assertRaises(KeyError):service.cancel(token)
 def test_reset_preserved(self):store.reservations[9]={'seats':1};store.reset();self.assertEqual(store.reservations,{})''')
 add('T11','intentionally_broken_repair','Repair unique.py stable_unique: keep the first occurrence in original order, including 0, False and empty string according to normal Python equality. Do not sort. Preserve checksum(values). Validate and repair using exact failures.',
 {'unique.py':'def stable_unique(values):\n    return sorted(set(v for v in values if v))\ndef checksum(values):\n    return sum(values)\n'},
 {'unique.py':'def stable_unique(values):\n    result=[]\n    for v in values:\n        if v not in result:result.append(v)\n    return result\ndef checksum(values):\n    return sum(values)\n'},
 '''import unique
class Check(unittest.TestCase):
 def test_order(self):self.assertEqual(unique.stable_unique([3,1,3,2]),[3,1,2])
 def test_zero(self):self.assertEqual(unique.stable_unique([0,False,2,0]),[0,2])
 def test_empty(self):self.assertEqual(unique.stable_unique(['','a','','b']),['','a','b'])
 def test_preserved(self):self.assertEqual(unique.checksum([1,2,3]),6)''')
 for id,category,mode in [('T12','cancellation','cancel'),('T13','stale_revision','conflict'),('T14','explicit_acceptance','accept'),('T15','rejection_nonpublication','reject')]:
  add(id,category,'Edit lifecycle.py value() to return integer 31. Preserve unrelated files. Validate the supplied tests.',
   {'lifecycle.py':'def value():\n    return 4\n'}, {'lifecycle.py':'def value():\n    return 31\n'},
   '''import lifecycle
class Check(unittest.TestCase):
 def test_value(self):self.assertEqual(lifecycle.value(),31)
 def test_integer(self):self.assertIsInstance(lifecycle.value(),int)''',mode)
 return c
def freeze():
 path=OUT/'reports/tasks.json'
 if path.exists():raise RuntimeError('Suite already frozen')
 data=cases();path.write_text(json.dumps(data,indent=2),encoding='utf-8')
 (OUT/'reports/tasks.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest())
 print('Frozen 15 new task categories; '+str(path),flush=True)
if __name__=='__main__':freeze()
