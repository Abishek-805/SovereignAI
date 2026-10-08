"""Trusted framework probes. Reports runtime scope; never invents business oracles."""
import ast
import json
import re

def node_probe(entry,source,require_json=False,require_invalid=False):
    port=re.search(r'\.listen\(\s*(\d+)|\b(?:const|let|var)\s+(?:PORT|port)\s*=\s*(\d+)',source)
    port=int(next(value for value in port.groups() if value)) if port else 8766
    if 'process.env.PORT' in source:port=8766
    routes=list(dict.fromkeys(['/']+re.findall(r"(?:\.get\(|(?:url|pathname)\s*===?\s*)\s*['\"](/[^'\"]*)['\"]",source)+['/health']))
    return '''import json,os,subprocess,time,urllib.request,urllib.error
log=open('/output/node-readiness.log','w+')
proc=subprocess.Popen(['node',ENTRY],stdout=log,stderr=log,env={**os.environ,'PORT':str(PORT)})
observed=[]
try:
 success=False
 for attempt in range(50):
  if proc.poll() is not None:raise RuntimeError('Node process exited before readiness')
  for route in ROUTES:
   try:
    response=urllib.request.urlopen('http://127.0.0.1:'+str(PORT)+route,timeout=1)
    if response.status!=200:continue
    body=response.read(65536)
    if JSON_REQUIRED:
     try:json.loads(body)
     except ValueError:continue
    observed.append({'method':'GET','path':route,'status':response.status,'json_checked':JSON_REQUIRED})
    success=True;break
   except urllib.error.HTTPError:continue
   except (OSError,TimeoutError):continue
  if success:break
  time.sleep(.1)
 assert success,'Node server did not serve a successful GET response'
 if INVALID:
  posts=list(dict.fromkeys(POSTS))
  assert posts,'No discoverable POST endpoint for invalid JSON validation'
  for route in posts:
   request=urllib.request.Request('http://127.0.0.1:'+str(PORT)+route,data=b'{broken',headers={'Content-Type':'application/json'})
   try:
    response=urllib.request.urlopen(request,timeout=2)
    raise AssertionError('Malformed JSON accepted at '+route)
   except urllib.error.HTTPError as error:
    assert error.code in (400,422),'Invalid JSON did not produce a client input error'
    if JSON_REQUIRED:
     body=error.read(65536)
     try:json.loads(body)
     except ValueError:raise AssertionError('POST '+route+' returned HTTP '+str(error.code)+' with a non-JSON error response: '+body[:150].decode('utf-8',errors='replace'))
    observed.append({'method':'POST','path':route,'status':error.code,'invalid_json_rejected':True})
 print('INDEPENDENT_FRAMEWORK_PROBE='+json.dumps(observed),flush=True)
finally:
 proc.terminate()
 try:proc.wait(timeout=3)
 except subprocess.TimeoutExpired:proc.kill();proc.wait()
 log.close()
'''.replace('ENTRY',repr(entry)).replace('str(PORT)',repr(str(port))).replace('ROUTES',repr(routes)).replace('JSON_REQUIRED',repr(require_json)).replace('INVALID',repr(require_invalid)).replace('POSTS',repr(re.findall(r"\.post\(\s*['\"](/[^'\"]*)['\"]",source)))

def flask_probe(entry,require_json=False,require_invalid=False):
    return '''import importlib.util,json,os,subprocess,sys,time,urllib.request,urllib.error
from pathlib import Path
target=Path(ENTRY)
sys.path.insert(0,str(target.parent.resolve()))
spec=importlib.util.spec_from_file_location('agent_probe_app',target)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
from flask import Flask
apps=[value for value in vars(module).values() if isinstance(value,Flask)]
if not apps and callable(getattr(module,'create_app',None)):apps=[module.create_app()]
assert len(apps)==1,'No unique Flask application was discovered'
app=apps[0]
gets=[rule.rule for rule in app.url_map.iter_rules() if 'GET' in rule.methods and '<' not in rule.rule and rule.endpoint!='static']
posts=[rule.rule for rule in app.url_map.iter_rules() if 'POST' in rule.methods and '<' not in rule.rule]
assert gets,'No observable GET endpoint exists'
if INVALID:assert posts,'No POST endpoint exists to check invalid JSON handling'
log=open('/output/readiness.log','w+')
proc=subprocess.Popen([sys.executable,'-m','flask','--app',str(target),'run','--no-reload','--host','127.0.0.1','--port','8765'],stdout=log,stderr=log)
observed=[]
try:
 success=False
 for attempt in range(50):
  if proc.poll() is not None:raise RuntimeError('Flask process exited before readiness')
  for route in gets:
   try:
    response=urllib.request.urlopen('http://127.0.0.1:8765'+route,timeout=1)
    if response.status!=200:continue
    body=response.read(65536)
    if JSON_REQUIRED:
     try:json.loads(body)
     except ValueError:continue
    observed.append({'method':'GET','path':route,'status':response.status,'json_checked':JSON_REQUIRED})
    success=True;break
   except (OSError,TimeoutError):continue
  if success:break
  time.sleep(.1)
 else:raise RuntimeError('Flask server did not become ready')
 if INVALID:
  for route in posts:
   request=urllib.request.Request('http://127.0.0.1:8765'+route,data=b'{broken',headers={'Content-Type':'application/json'})
   try:
    response=urllib.request.urlopen(request,timeout=2)
    raise AssertionError('Malformed JSON accepted at '+route)
   except urllib.error.HTTPError as error:
    assert error.code in (400,422),'Malformed JSON did not produce a client input error'
    if JSON_REQUIRED:
     body=error.read(65536)
     try:json.loads(body)
     except ValueError:raise AssertionError('POST '+route+' returned HTTP '+str(error.code)+' with a non-JSON error response: '+body[:150].decode('utf-8',errors='replace'))
    observed.append({'method':'POST','path':route,'status':error.code,'invalid_json_rejected':True})
 print('INDEPENDENT_FRAMEWORK_PROBE='+json.dumps(observed),flush=True)
finally:
 proc.terminate()
 try:proc.wait(timeout=3)
 except subprocess.TimeoutExpired:proc.kill();proc.wait()
 log.close()
'''.replace('ENTRY',repr(entry)).replace('JSON_REQUIRED',repr(require_json)).replace('INVALID',repr(require_invalid))

def executable_candidates(files,changed):
    candidates=[]
    for name in changed:
        data=files.get(name)
        if not data or not name.endswith('.py') or name.split('/')[-1].startswith('test_'):continue
        try:tree=ast.parse(data.decode('utf-8'))
        except (SyntaxError,UnicodeError):continue
        if any(isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='Flask' for node in ast.walk(tree)):
            candidates.append(name)
    return candidates
