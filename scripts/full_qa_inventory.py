import ast,csv,hashlib,json,re,subprocess,time,urllib.request,urllib.error
from pathlib import Path
ROOT=Path.cwd(); OUT=ROOT/'outputs/full-qa-audit'; OUT.mkdir(exist_ok=True,parents=True)
def save(name,obj):
 p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():p.with_name(p.name+'.previous-'+str(time.time_ns())).write_bytes(p.read_bytes())
 p.write_text(json.dumps(obj,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
def http(path,method='GET',data=None,headers=None,raw=None):
 start=time.monotonic(); body=raw if raw is not None else json.dumps(data).encode() if data is not None else None
 req=urllib.request.Request('http://127.0.0.1:8088'+path,data=body,method=method,headers={'Content-Type':'application/json',**(headers or {})})
 try:
  with urllib.request.urlopen(req,timeout=180) as r:code=r.status;h=dict(r.headers);b=r.read()
 except urllib.error.HTTPError as e:code=e.code;h=dict(e.headers);b=e.read()
 except Exception as e:return {'path':path,'method':method,'status':None,'error':str(e),'latency':time.monotonic()-start}
 try:content=json.loads(b)
 except Exception:content=b.decode('utf-8',errors='replace')[:10000]
 return {'path':path,'method':method,'request':data if raw is None else raw.decode(errors='replace'),'status':code,'headers':h,'body':content,'latency':time.monotonic()-start}
if __name__=='__main__':
 inventory=[];backend=[];ui=[]; routes=[]
 for directory in ['backend','router','rag','workflows','agent','skills','scripts','frontend/llama-ui/src']:
  for p in (ROOT/directory).rglob('*'):
   if not p.is_file() or p.suffix not in ['.py','.svelte','.ts','.js','.md','.ps1','.json','.bat']:continue
   loc=p.relative_to(ROOT).as_posix();text=p.read_text(encoding='utf-8',errors='replace');category='frontend' if loc.startswith('frontend') else 'skill' if p.name=='SKILL.md' else directory
   item={'id':loc,'category':category,'source_location':loc,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'ui_location':None,'api_location':None,'status':'UNTESTABLE','reason':'Source inventoried; individual behavior requires mapped runtime evidence'}
   inventory.append(item)
   if p.suffix=='.py':
    try:t=ast.parse(text)
    except SyntaxError:continue
    entries=[{'name':n.name,'line':n.lineno,'kind':type(n).__name__} for n in ast.walk(t) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))]
    backend.append({**item,'entry_points':entries,'dependencies':[ast.unparse(n) for n in t.body if isinstance(n,(ast.Import,ast.ImportFrom))]})
    for n in ast.walk(t):
     if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
     for d in n.decorator_list:
      if isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and isinstance(d.func.value,ast.Name) and d.func.value.id=='app' and d.func.attr in ['get','post','put','patch','delete','api_route'] and d.args and isinstance(d.args[0],ast.Constant):
       methods=[d.func.attr.upper()] if d.func.attr!='api_route' else next((ast.literal_eval(k.value) for k in d.keywords if k.arg=='methods'),[])
       for method in methods:routes.append({'id':method+' '+d.args[0].value,'method':method,'path':d.args[0].value,'handler':n.name,'source_location':loc+':'+str(n.lineno),'status':'UNTESTABLE','reason':'Pending runtime coverage'})
   elif p.suffix=='.svelte':
    controls=[]
    for match in re.finditer(r'<(button|input|select|textarea|dialog|a|form)\b[^>]*>',text):
     tag=match.group();line=text.count('\n',0,match.start())+1
     controls.append({'id':loc+':'+str(line)+':'+str(match.start()),'type':match.group(1),'source_location':loc+':'+str(line),'markup':tag[:600],'status':'UNTESTABLE','reason':'Static template control; dynamic instances require browser interaction'})
    ui.append({**item,'controls':controls})
 save('inventory/system-inventory.json',inventory);save('system-inventory.json',inventory);save('backend-inventory.json',backend);save('ui-inventory.json',ui);save('api-inventory.json',routes);save('api/inventory.json',routes)
 for path,name in [('/health','backend/health.json'),('/status','inventory/runtime-status.json'),('/workbench/info','inventory/workbench-info.json'),('/openapi.json','api/openapi.json'),('/tools','inventory/tools.json'),('/v1/models','model/models.json'),('/v1/props','model/props.json')]:save(name,http(path))
 print(json.dumps({'source_items':len(inventory),'backend_modules':len(backend),'ui_components':len(ui),'static_controls':sum(len(i['controls']) for i in ui),'api_routes':len(routes)}))
