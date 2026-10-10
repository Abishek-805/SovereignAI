"""Distinct JS/TS/React/Flask/SQL references with pinned offline Docker oracles."""
import hashlib,json,sys
from pathlib import Path
from experiments.dataset_expansion.prepare import ROOT,IMAGE,rows,save,jsonl,digest
from experiments.dataset_expansion.references import sample,message
from router.sandbox import CodeSandbox

CASES=[
 ('js-topology','javascript','Topologically sort explicit nodes and directed edge pairs. Use lexical tie breaking, ignore duplicate edges, reject unknown nodes and cycles. Preserve inputs.',r'''function order(nodes, edges) {
 const degree=new Map(nodes.map(n=>[n,0])), next=new Map(nodes.map(n=>[n,new Set()]));
 for(const [a,b] of edges){if(!degree.has(a)||!degree.has(b))throw new Error('unknown node');if(!next.get(a).has(b)){next.get(a).add(b);degree.set(b,degree.get(b)+1);}}
 const ready=nodes.filter(n=>degree.get(n)===0).sort(), result=[];
 while(ready.length){const n=ready.shift();result.push(n);for(const b of next.get(n)){degree.set(b,degree.get(b)-1);if(degree.get(b)===0){ready.push(b);ready.sort();}}}
 if(result.length!==nodes.length)throw new Error('cycle');return result;
} module.exports={order};''',r'''const n=['c','a','b'];a.deepStrictEqual(m.order(n,[['a','c'],['a','c']]),['a','b','c']);a.deepStrictEqual(n,['c','a','b']);a.deepStrictEqual(m.order([],[]),[]);a.throws(()=>m.order(['a'],[['a','a']]));a.throws(()=>m.order(['a'],[['a','b']]));'''),
 ('js-intervals','javascript','Merge overlapping closed numeric intervals into sorted disjoint intervals without mutating input. Touching endpoints overlap. Reject reversed intervals.',r'''function merge(intervals){const v=intervals.map(([a,b])=>{if(a>b)throw new Error('reversed');return [a,b];}).sort((x,y)=>x[0]-y[0]);const out=[];for(const p of v){const last=out[out.length-1];if(last&&p[0]<=last[1])last[1]=Math.max(last[1],p[1]);else out.push(p);}return out;} module.exports={merge};''',r'''const v=[[5,8],[1,3],[3,6],[10,11]];a.deepStrictEqual(m.merge(v),[[1,8],[10,11]]);a.deepStrictEqual(v,[[5,8],[1,3],[3,6],[10,11]]);a.deepStrictEqual(m.merge([]),[]);a.throws(()=>m.merge([[3,1]]));'''),
 ('js-query','javascript','Parse a URL query into a null-prototype object of arrays, decoding percent escapes and plus spaces and preserving duplicate-key order. Handle __proto__ as ordinary data.',r'''function query(text){const result=Object.create(null);for(const [k,v] of new URLSearchParams(text)){if(!Object.hasOwn(result,k))result[k]=[];result[k].push(v);}return result;}module.exports={query};''',r'''const r=m.query('a=1&a=2&word=two+words&__proto__=x');a.deepStrictEqual(r.a,['1','2']);a.deepStrictEqual(r.word,['two words']);a.deepStrictEqual(r.__proto__,['x']);a.strictEqual(Object.getPrototypeOf(r),null);a.deepStrictEqual(Object.keys(m.query('')),[]);'''),
 ('js-sequential','javascript','Run asynchronous task functions strictly in sequence, return ordered results, and stop immediately on rejection without starting later tasks.',r'''async function run(tasks){const results=[];for(const task of tasks)results.push(await task());return results;}module.exports={run};''',r'''(async()=>{const log=[];const result=await m.run([async()=>{log.push('first');return 1},async()=>{log.push('second');return 2}]);a.deepStrictEqual(result,[1,2]);a.deepStrictEqual(log,['first','second']);await a.rejects(()=>m.run([async()=>{throw new Error('bad')},async()=>log.push('unexpected')]));a.deepStrictEqual(log,['first','second']);a.deepStrictEqual(await m.run([]),[]);})().catch(e=>{console.error(e);process.exit(1)});'''),
 ('ts-clamp','typescript','Export typed clamp(value,low,high); reject non-finite arguments and reversed bounds. Return the nearest bound for out-of-range values.',r'''export function clamp(value:number,low:number,high:number):number{if(!Number.isFinite(value)||!Number.isFinite(low)||!Number.isFinite(high)||low>high)throw new Error('invalid bounds');return Math.min(high,Math.max(low,value));}''',r'''a.strictEqual(m.clamp(4,0,3),3);a.strictEqual(m.clamp(-1,0,3),0);a.strictEqual(m.clamp(2,0,3),2);a.throws(()=>m.clamp(NaN,0,3));a.throws(()=>m.clamp(0,3,1));a.throws(()=>m.clamp(0,0,Infinity));'''),
 ('ts-result','typescript','Define a discriminated Result<T> union and mapResult that maps only success values, preserving an error without calling the mapping function.',r'''export type Result<T>={ok:true,value:T}|{ok:false,error:string};export function mapResult<A,B>(result:Result<A>,fn:(value:A)=>B):Result<B>{return result.ok?{ok:true,value:fn(result.value)}:result;}''',r'''a.deepStrictEqual(m.mapResult({ok:true,value:3},x=>x*2),{ok:true,value:6});const err={ok:false,error:'offline'};a.strictEqual(m.mapResult(err,()=>{throw Error('called')}),err);'''),
 ('ts-reading','typescript','Parse unknown data into a typed reading with string sensor and finite numeric value. Reject null, arrays, booleans as values and missing fields. Do not mutate input.',r'''export type Reading={sensor:string,value:number};export function parseReading(input:unknown):Reading{if(!input||typeof input!=='object'||Array.isArray(input))throw new Error('object required');const r=input as Record<string,unknown>;if(typeof r.sensor!=='string'||typeof r.value!=='number'||!Number.isFinite(r.value))throw new Error('invalid reading');return {sensor:r.sensor,value:r.value};}''',r'''const v={sensor:'north',value:12,extra:'keep'};a.deepStrictEqual(m.parseReading(v),{sensor:'north',value:12});a.strictEqual(v.extra,'keep');for(const x of [null,[],{sensor:'n',value:true},{sensor:'n',value:Infinity},{value:1}])a.throws(()=>m.parseReading(x));'''),
 ('ts-grouping','typescript','Export generic groupBy(items,key) preserving item order within each group. Use own data groups that safely support keys constructor and __proto__. Empty input returns no groups.',r'''export function groupBy<T>(items:readonly T[],key:(item:T)=>string):Record<string,T[]>{const result:Record<string,T[]>=Object.create(null);for(const item of items){const k=key(item);if(!Object.prototype.hasOwnProperty.call(result,k))result[k]=[];result[k].push(item);}return result;}''',r'''const items=[{g:'__proto__',n:1},{g:'x',n:2},{g:'__proto__',n:3},{g:'constructor',n:4}];const r=m.groupBy(items,x=>x.g);a.deepStrictEqual(r.__proto__.map(x=>x.n),[1,3]);a.deepStrictEqual(r.constructor.map(x=>x.n),[4]);a.strictEqual(Object.getPrototypeOf(r),null);a.deepStrictEqual(Object.keys(m.groupBy([],x=>x)),[]);'''),
 ('react-alert','react','Create a stateless React Alert component. Render a role=alert paragraph for a nonempty message and nothing for an empty message. React must escape message text; no client event behavior is requested.',r'''const React=require('react');function Alert({message}){return message?React.createElement('p',{role:'alert'},message):null;}module.exports={Alert};''',r'''a.strictEqual(render(React.createElement(m.Alert,{message:''})), '');a.strictEqual(render(React.createElement(m.Alert,{message:'<script>alert(1)</script>'})), '<p role="alert">&lt;script&gt;alert(1)&lt;/script&gt;</p>');'''),
 ('react-list','react','Create a stateless React List component. Show a No records paragraph for an empty collection; otherwise an unordered list of escaped name values using record IDs as keys.',r'''const React=require('react');function List({items}){return items.length?React.createElement('ul',null,items.map(item=>React.createElement('li',{key:item.id},item.name))):React.createElement('p',null,'No records');}module.exports={List};''',r'''a.strictEqual(render(React.createElement(m.List,{items:[]})), '<p>No records</p>');a.strictEqual(render(React.createElement(m.List,{items:[{id:'b',name:'B'},{id:'a',name:'<A>'}]})), '<ul><li>B</li><li>&lt;A&gt;</li></ul>');'''),
 ('react-navigation','react','Create a stateless React Navigation component from links with id,href,label. Mark exactly the matching active ID with aria-current=page, preserve hrefs and safely escape labels.',r'''const React=require('react');function Navigation({links,activeId}){return React.createElement('nav',{'aria-label':'Primary'},links.map(link=>React.createElement('a',{key:link.id,href:link.href,'aria-current':link.id===activeId?'page':undefined},link.label)));}module.exports={Navigation};''',r'''a.strictEqual(render(React.createElement(m.Navigation,{links:[{id:'a',href:'/a',label:'A'},{id:'b',href:'/b',label:'B'}],activeId:'b'})), '<nav aria-label="Primary"><a href="/a">A</a><a href="/b" aria-current="page">B</a></nav>');'''),
 ('react-summary','react','Create a stateless React Totals component showing the sum of finite record amount values in an output element with aria-label Total. Reject non-finite amounts. Do not mutate records.',r'''const React=require('react');function Totals({records}){const total=records.reduce((sum,r)=>{if(!Number.isFinite(r.amount))throw Error('invalid amount');return sum+r.amount;},0);return React.createElement('output',{'aria-label':'Total'},String(total));}module.exports={Totals};''',r'''const r=[{amount:2},{amount:3}];a.strictEqual(render(React.createElement(m.Totals,{records:r})), '<output aria-label="Total">5</output>');a.strictEqual(render(React.createElement(m.Totals,{records:[]})), '<output aria-label="Total">0</output>');a.deepStrictEqual(r,[{amount:2},{amount:3}]);a.throws(()=>render(React.createElement(m.Totals,{records:[{amount:NaN}]})));'''),
 ('flask-greeting','flask','Provide create_app returning a Flask app with GET /hello. Read name from query parameters, default world, return JSON greeting without interpreting HTML. Preserve GET /health returning status ok.',r'''from flask import Flask,request,jsonify
def create_app():
 app=Flask(__name__)
 @app.get('/health')
 def health():return jsonify(status='ok')
 @app.get('/hello')
 def hello():return jsonify(greeting='Hello, '+request.args.get('name','world'))
 return app
''',r'''c=m.create_app().test_client();assert c.get('/hello').get_json()=={'greeting':'Hello, world'};assert c.get('/hello?name=%3Cscript%3E').get_json()=={'greeting':'Hello, <script>'};assert c.get('/health').get_json()=={'status':'ok'}'''),
 ('flask-json-boundary','flask','Provide create_app with POST /double requiring a JSON object containing an integer value. Reject missing/invalid JSON with 415, other shapes and booleans with 400. Return JSON doubled result and retain /health.',r'''from flask import Flask,request,jsonify
def create_app():
 app=Flask(__name__)
 @app.get('/health')
 def health():return jsonify(status='ok')
 @app.post('/double')
 def double():
  if not request.is_json:return jsonify(error='JSON required'),415
  body=request.get_json(silent=True)
  if body is None:return jsonify(error='JSON required'),415
  if not isinstance(body,dict) or type(body.get('value')) is not int:return jsonify(error='integer required'),400
  return jsonify(result=body['value']*2)
 return app
''',r'''c=m.create_app().test_client();assert c.post('/double',json={'value':4}).get_json()=={'result':8};assert c.post('/double',data='raw').status_code==415;assert c.post('/double',data='{',content_type='application/json').status_code==415;assert c.post('/double',json={'value':True}).status_code==400;assert c.post('/double',json=[]).status_code==400;assert c.get('/health').get_json()=={'status':'ok'}'''),
 ('flask-state','flask','Provide create_app with pending job A. POST /jobs/<id> accepts JSON state and permits only pending->running->done. Unknown IDs return 404, invalid transitions 409 and invalid bodies 400. GET retrieves current state; failed transitions do not mutate it.',r'''from flask import Flask,request,jsonify
def create_app():
 app=Flask(__name__);jobs={'A':'pending'};allowed={'pending':'running','running':'done'}
 @app.route('/jobs/<identity>',methods=['GET','POST'])
 def job(identity):
  if identity not in jobs:return jsonify(error='unknown'),404
  if request.method=='GET':return jsonify(state=jobs[identity])
  data=request.get_json(silent=True)
  if not isinstance(data,dict) or not isinstance(data.get('state'),str):return jsonify(error='invalid body'),400
  if allowed.get(jobs[identity])!=data['state']:return jsonify(error='invalid transition'),409
  jobs[identity]=data['state'];return jsonify(state=jobs[identity])
 return app
''',r'''c=m.create_app().test_client();assert c.post('/jobs/A',json={'state':'done'}).status_code==409;assert c.get('/jobs/A').get_json()=={'state':'pending'};assert c.post('/jobs/A',json={'state':'running'}).status_code==200;assert c.post('/jobs/A',json={'state':'done'}).get_json()=={'state':'done'};assert c.post('/jobs/A',json={}).status_code==400;assert c.get('/jobs/B').status_code==404'''),
 ('flask-pagination','flask','Provide create_app with GET /items returning a slice of integers 0..9. Default offset 0 and limit 3; validate integer offset>=0 and limit 1..5. Invalid parameters return JSON 400. An offset beyond the collection returns an empty list.',r'''from flask import Flask,request,jsonify
def create_app():
 app=Flask(__name__)
 @app.get('/items')
 def items():
  try:offset=int(request.args.get('offset','0'));limit=int(request.args.get('limit','3'))
  except ValueError:return jsonify(error='integer required'),400
  if offset<0 or not 1<=limit<=5:return jsonify(error='invalid range'),400
  return jsonify(items=list(range(10))[offset:offset+limit])
 return app
''',r'''c=m.create_app().test_client();assert c.get('/items').get_json()=={'items':[0,1,2]};assert c.get('/items?offset=8&limit=5').get_json()=={'items':[8,9]};assert c.get('/items?offset=100').get_json()=={'items':[]};assert c.get('/items?offset=-1').status_code==400;assert c.get('/items?limit=0').status_code==400;assert c.get('/items?limit=bad').status_code==400'''),
 ('sql-cascade','sql','Create SQLite parents(id primary key) and children(id primary key,parent_id not null). Enable foreign keys and cascade child deletion when its parent is explicitly deleted.',r'''PRAGMA foreign_keys=ON;CREATE TABLE parents(id INTEGER PRIMARY KEY);CREATE TABLE children(id INTEGER PRIMARY KEY,parent_id INTEGER NOT NULL REFERENCES parents(id) ON DELETE CASCADE);''',r'''c.execute('INSERT INTO parents VALUES(1)');c.execute('INSERT INTO children VALUES(2,1)');c.execute('DELETE FROM parents WHERE id=1');assert c.execute('SELECT COUNT(*) FROM children').fetchone()==(0,)
try:c.execute('INSERT INTO children VALUES(3,99)');raise AssertionError('orphan accepted')
except sqlite3.IntegrityError:pass'''),
 ('sql-running','sql','Create readings(sensor text,tick integer,value real) and a cumulative view adding values per sensor in tick order using explicit ROWS window semantics.',r'''CREATE TABLE readings(sensor TEXT,tick INTEGER,value REAL);CREATE VIEW cumulative AS SELECT sensor,tick,value,SUM(value) OVER(PARTITION BY sensor ORDER BY tick ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS total FROM readings;''',r'''c.executemany('INSERT INTO readings VALUES(?,?,?)',[('n',2,3),('s',1,10),('n',1,2)]);assert c.execute('SELECT sensor,tick,total FROM cumulative ORDER BY sensor,tick').fetchall()==[('n',1,2.0),('n',2,5.0),('s',1,10.0)]'''),
 ('sql-null-stats','sql','Create samples(group_name text,value real) and stats view with per-group observed_count, missing_count and mean. Exclude NULL from observed count and mean; retain all-NULL groups.',r'''CREATE TABLE samples(group_name TEXT,value REAL);CREATE VIEW stats AS SELECT group_name,COUNT(value) AS observed_count,COUNT(*)-COUNT(value) AS missing_count,AVG(value) AS mean FROM samples GROUP BY group_name;''',r'''c.executemany('INSERT INTO samples VALUES(?,?)',[('a',2),('a',4),('a',None),('b',None)]);assert c.execute('SELECT * FROM stats ORDER BY group_name').fetchall()==[('a',2,1,3.0),('b',0,1,None)]'''),
 ('sql-normalized-unique','sql','Create users(id integer primary key, username text not null). Reject blank/space-only usernames, and enforce uniqueness ignoring surrounding ASCII spaces and case.',r'''CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT NOT NULL CHECK(length(trim(username))>0));CREATE UNIQUE INDEX normalized_username ON users(lower(trim(username)));''',r'''c.execute("INSERT INTO users VALUES(1,'Alice')")
for name in [' alice ','','   ']:
 try:c.execute('INSERT INTO users(username) VALUES(?)',(name,));raise AssertionError('invalid or duplicate accepted')
 except sqlite3.IntegrityError:pass
c.execute("INSERT INTO users(username) VALUES('Bob')");assert c.execute('SELECT COUNT(*) FROM users').fetchone()==(2,)'''),
]

def main(out):
    frozen=out/'polyglot-definitions.json'
    if not frozen.exists():save(frozen,{'cases':CASES,'frozen_before_execution':True})
    assert json.loads(frozen.read_text(encoding='utf-8'))['cases']==json.loads(json.dumps(CASES))
    dependencies={};base=ROOT/'frontend/llama-ui/node_modules'
    for package in ('typescript','react','react-dom'):
        directory=base/package;metadata=json.loads((directory/'package.json').read_text(encoding='utf-8'))
        for path in directory.rglob('*'):
            if not path.is_file():continue
            name=str(path.relative_to(base)).replace('\\','/')
            if package=='typescript' and not (name.endswith('lib/typescript.js') or '/lib/lib.' in name and name.endswith('.d.ts') or path.name in {'package.json','LICENSE.txt'}):continue
            if package!='typescript' and path.suffix not in {'.js','.json'} and not path.name.startswith('LICENSE'):continue
            dependencies['node_modules/'+name]=path.read_bytes()
        save(out/(package+'-offline-runtime.json'),{'version':metadata['version'],'license':metadata['license'],'source':'existing installed public dependency; no production files changed','sha256':{name:hashlib.sha256(data).hexdigest() for name,data in dependencies.items() if name.startswith('node_modules/'+package+'/')}})
    raw=out/'polyglot-raw';raw.mkdir(exist_ok=True);sandbox=CodeSandbox('docker',IMAGE,out/'polyglot-sandbox');positive=[];negative=[]
    for identity,language,request,code,test in CASES:
        directory=raw/identity;directory.mkdir(exist_ok=True)
        if (directory/'outcome.json').exists():
            r=json.loads((directory/'outcome.json').read_text(encoding='utf-8'));(positive if r['quality']['verified'] else negative).append(r);continue
        filename='main.ts' if language=='typescript' else 'main.py' if language=='flask' else 'main.sql' if language=='sql' else 'main.js'
        files={filename:code.encode(),'sentinel.txt':b'UNCHANGED\n'}
        if language=='typescript':files.update({n:b for n,b in dependencies.items() if n.startswith('node_modules/typescript/')})
        if language=='react':files.update({n:b for n,b in dependencies.items() if not n.startswith('node_modules/typescript/')})
        header="import os,sys,shutil\nfrom pathlib import Path\nshutil.copytree('/input','/output/project',ignore=lambda p,n:{'program.py'} if p=='/input' else set());os.chdir('/output/project');sys.path.insert(0,'/output/project')\n"
        if language=='flask':runner=header+'import main as m\n'+test+'\n'
        elif language=='sql':runner=header+"import sqlite3\nc=sqlite3.connect(':memory:');c.executescript(Path('main.sql').read_text())\n"+test+'\n'
        else:
            compiler="const ts=require('./node_modules/typescript/lib/typescript.js');const options={target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,strict:true,noEmitOnError:true,outDir:'compiled'};const program=ts.createProgram(['main.ts'],options);const errors=ts.getPreEmitDiagnostics(program);if(errors.length){console.error(ts.formatDiagnosticsWithColorAndContext(errors,{getCurrentDirectory:()=>process.cwd(),getCanonicalFileName:x=>x,getNewLine:()=> '\\n'}));process.exit(1)}program.emit();" if language=='typescript' else ''
            js="const a=require('assert');const m=require('./"+('compiled/main.js' if language=='typescript' else 'main.js')+"');"
            if language=='react':js="process.env.NODE_ENV='production';const React=require('react');const render=require('react-dom/server').renderToStaticMarkup;"+js
            files['oracle.cjs']=(compiler+js+test).encode()
            runner=header+"import subprocess\nsubprocess.run(['node','oracle.cjs'],check=True)\n"
        runner+="assert Path('sentinel.txt').read_bytes()==b'UNCHANGED\\n'\nprint('INDEPENDENT_PASS')\n"
        (directory/'oracle.py').write_text(runner,encoding='utf-8')
        result=sandbox.execute(runner,input_files=files,timeout=45)
        save(directory/'oracle.json',{'executed':result.executed,'exit_code':result.exit_code,'stdout':result.stdout,'stderr':result.stderr,'image':IMAGE,'candidate_sha256':hashlib.sha256(code.encode()).hexdigest()})
        bad={**files,filename:(b'' if language=='sql' else b'')}
        control=sandbox.execute(runner,input_files=bad,timeout=45)
        save(directory/'negative-control.json',{'executed':control.executed,'exit_code':control.exit_code,'stdout':control.stdout,'stderr':control.stderr})
        passed=result.executed and result.exit_code==0 and control.executed and control.exit_code!=0
        row=sample('polyglot-'+identity,'coding','polyglot:'+identity,[message('system','Return the requested complete implementation using the specified language. Do not claim validation without evidence.'),message('user',request),message('assistant','```'+language+'\n'+code+'\n```')],{'kind':'offline_codex_reference','teacher':'Codex authored reference, not laptop model output','license':'operator-authored fixture','runtime_dependencies':'pinned existing TypeScript Apache-2.0 and React/ReactDOM MIT; Docker unchanged'},{'type':'preauthored distinct behavioral Docker assertions plus empty-implementation negative control and preservation','passed':passed,'evidence':str((directory/'oracle.json').relative_to(ROOT))},language=language,repair=False,capability=identity)
        row['quality']['verified']=passed
        if not passed:row['rejection']='DOCKER_ORACLE_OR_NEGATIVE_CONTROL_FAILED'
        save(directory/'outcome.json',row);(positive if passed else negative).append(row);jsonl(out/'polyglot-verified.jsonl',positive);jsonl(out/'polyglot-negatives.jsonl',negative);print(identity,passed,flush=True)

if __name__=='__main__':main(Path(sys.argv[1]).resolve())
