"""Request-bound obligations and trusted Docker checks, independent of worker source.

The compiler deliberately recognises only literal, unambiguous obligations. It
does not pretend that a model-authored checklist proves arbitrary semantics.
"""
import hashlib
import ast
import json
import re
from pathlib import PurePosixPath


REQUIREMENT_CLASSES = ('FILE', 'INTERFACE', 'NORMAL', 'INVALID_INPUT', 'ERROR',
                       'OUTPUT', 'PERSISTENCE', 'PRESERVATION', 'ENTRYPOINT', 'ACCEPTANCE')


def independent_exception_cases(files):
    """Read literal unittest exception cases without executing fixture code.

    Only immutable supplied tests are eligible. Unknown expressions, control
    flow and values are skipped; the original suite remains the authority.
    """
    cases = []
    for name, data in files.items():
        if not PurePosixPath(name).name.startswith('test_') or not name.endswith('.py'):
            continue
        try:
            tree = ast.parse(data.decode('utf-8'))
        except (SyntaxError, UnicodeError):
            continue
        imports = {alias.asname or alias.name: (node.module, alias.name)
                   for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
                   for alias in node.names if alias.name != '*'}
        def value(node, env):
            if isinstance(node, ast.Name) and node.id in env:
                return env[node.id]
            return ast.literal_eval(node)
        def walk(nodes, env):
            for node in nodes:
                if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                    walk(node.body, {})
                elif isinstance(node, ast.For):
                    try:
                        values = value(node.iter, env)
                        if not isinstance(values, (list, tuple)) or len(values) > 32: continue
                        names = [node.target.id] if isinstance(node.target, ast.Name) else [n.id for n in node.target.elts]
                        for item in values:
                            parts = [item] if isinstance(node.target, ast.Name) else item
                            if len(names) != len(parts): continue
                            walk(node.body, {**env, **dict(zip(names, parts))})
                    except (ValueError, TypeError, AttributeError):
                        continue
                elif isinstance(node, ast.With):
                    for item in node.items:
                        expr = item.context_expr
                        if not (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute)
                                and expr.func.attr == 'assertRaises' and len(expr.args) == 1
                                and isinstance(expr.args[0], ast.Name)):
                            continue
                        exception = expr.args[0].id
                        if exception not in {'ValueError', 'TypeError', 'KeyError', 'IndexError', 'RuntimeError'}: continue
                        for statement in node.body:
                            call = statement.value if isinstance(statement, ast.Expr) else None
                            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id in imports): continue
                            try:
                                args = [value(arg, env) for arg in call.args]
                                kwargs = {kw.arg: value(kw.value, env) for kw in call.keywords if kw.arg}
                                if len(kwargs) != len(call.keywords): continue
                                if len(json.dumps([args, kwargs])) > 2000: continue
                            except (ValueError, TypeError): continue
                            module, symbol = imports[call.func.id]
                            cases.append({'kind': 'python_exception', 'file': module.replace('.', '/') + '.py',
                                          'symbol': symbol, 'args': args, 'kwargs': kwargs, 'expected': exception,
                                          'evidence': name + ':' + str(statement.lineno),
                                          'oracle_sha256': hashlib.sha256(data).hexdigest()})
        walk(tree.body, {})
    return cases[:64]


def file_contract(contract, path):
    """Compact task-bound obligations, retaining uncertain clauses explicitly."""
    own = [c for c in contract['acceptance_checks'] if c.get('file') == path]
    relevant={key:value for key,value in contract['requirement_classes'].items() if key not in {'ACCEPTANCE','INTERFACE','FILE'}}
    relevant.update(FILE=[path], INTERFACE=[c for c in own if c['kind'].startswith('python_')], ACCEPTANCE=own)
    return {'entrypoint': contract['entrypoint'], 'role': 'entrypoint' if path == contract['entrypoint'] else 'support',
            'requirements': relevant, 'acceptance_checks': own,
            'neighbor_interfaces': contract['interfaces'], 'error_behavior': contract['error_behavior'],
            'preservation_rules': contract['preservation_rules']}


def compile_contract(request, plan, files):
    operations=plan.get('operations',[])
    generated=[op['path'] for op in operations if op['action'] in {'create','edit'}]
    proposed=plan.get('contract') or {}
    entry=proposed.get('entrypoint','')
    checks=[]
    clauses=[clause.strip() for clause in re.split(r'(?<=[.!?])\s+',request) if clause.strip()]
    errors=[clause for clause in clauses if re.search(r'\breject(?:s|ed)?\b|\braise[sd]?\b|\binvalid\b|\bnonzero\b|\bmissing\b',clause,re.I)]
    persistence=[clause for clause in clauses if re.search(r'\bpersist\w*\b|\bappend\w*\b|\bstor(?:e|ed|age)\b|without losing',clause,re.I)]
    checks.extend(independent_exception_cases(files))
    # Literal calls in the authoritative request require no inferred business
    # rule or model-authored oracle. Non-literal expressions stay unresolved.
    for match in re.finditer(r'\b([A-Za-z_]\w*\.[A-Za-z_]\w*\([^\n;]*?\))\s+(?:must\s+)?raise\s+(ValueError|TypeError|KeyError|IndexError|RuntimeError)\b',request):
        try:
            call=ast.parse(match.group(1),mode='eval').body
            if not isinstance(call,ast.Call) or not isinstance(call.func,ast.Attribute):continue
            args=[ast.literal_eval(arg) for arg in call.args]
            kwargs={kw.arg:ast.literal_eval(kw.value) for kw in call.keywords if kw.arg}
            if len(kwargs)!=len(call.keywords) or len(json.dumps([args,kwargs]))>2000:continue
            checks.append({'kind':'python_exception','file':call.func.value.id+'.py','symbol':call.func.attr,
                           'args':args,'kwargs':kwargs,'expected':match.group(2),'evidence':match.group(0)})
        except (ValueError,SyntaxError,AttributeError,TypeError):continue
    # File names are obligations only when mentioned in the original request.
    names=re.findall(r'(?<![\w/])([\w./-]+\.(?:py|js|mjs|cjs|java|md|txt|json|html|css))\b',request)
    required=list(dict.fromkeys(names))
    for name in required:
        if name not in files:checks.append({'kind':'file','file':name,'evidence':name})
    for match in re.finditer(r'\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)\(\)\s+(?:must\s+)?return(?:s|ing)?\s+(-?\d+(?:\.\d+)?)\b',request,re.I):
        module,symbol,value=match.groups()
        checks.append({'kind':'python_return','file':module+'.py','symbol':symbol,'expected':float(value) if '.' in value else int(value),'evidence':match.group(0)})
    flags=[]
    for match in re.finditer(r'(--[A-Za-z][\w-]*)\s+(-?\d+(?:\.\d+)?)',request):
        flag,value=match.groups();flags.extend([flag,value])
    if flags and re.search(r'\bCLI\b|command.line',request,re.I):
        checks.append({'kind':'cli','file':entry,'args':flags,'exit':'zero','evidence':' '.join(flags)})
        if len(flags)==2 and re.search(r'reject\s+negative\b|negative\s+\w+\s+(?:must|should)\s+(?:fail|be rejected)',request,re.I):
            invalid=list(flags);invalid[1]='-1'
            checks.append({'kind':'cli','file':entry,'args':invalid,'exit':'nonzero','error_required':True,'evidence':'reject negative values'})
    printed=re.search(r'\bprints?\s+(?:exactly\s+)?(-?\d+)\b',request,re.I)
    quoted=re.search(r'\bprints?\s+(?:exactly\s+)?["\']([^"\'\n]{1,200})["\']',request,re.I)
    if printed and re.search(r'\bCLI\b|command.line',request,re.I):
        checks.append({'kind':'cli','file':entry,'args':flags,'exit':'zero','stdout':printed.group(1),'evidence':printed.group(0)})
    elif quoted and re.search(r'\bCLI\b|command.line',request,re.I):
        checks.append({'kind':'cli','file':entry,'args':flags,'exit':'zero','stdout':quoted.group(1),'evidence':quoted.group(0)})
    run_target=re.search(r'\b(?:run|execute)\s+([\w./-]+\.(?:py|js|mjs|cjs|java))\b',request,re.I)
    if not run_target and (printed or quoted) and not re.search(r'\b(?:do not|never|without)\s+(?:run|execute)',request,re.I):
        # Bind an output-preservation obligation to a unique existing executable,
        # independently of the worker's proposed entrypoint. Parse, never execute,
        # source while constructing context on the host.
        executables=[]
        for name,data in files.items():
            if not name.endswith('.py') or PurePosixPath(name).name.startswith('test_'):continue
            try:tree=ast.parse(data.decode('utf-8'))
            except (SyntaxError,UnicodeError):continue
            if any(isinstance(node,ast.Expr) and isinstance(node.value,ast.Call)
                   and isinstance(node.value.func,ast.Name) and node.value.func.id=='print'
                   for node in tree.body):executables.append(name)
        if len(executables)==1:
            checks.append({'kind':'cli','file':executables[0],'args':flags,'exit':'zero',
                           'stdout':(printed or quoted).group(1),'evidence':(printed or quoted).group(0)})
    if run_target and (printed or quoted):
        from router.tool_registry import explicit_operation_requested
        if explicit_operation_requested(request,'file_run'):
            checks.append({'kind':'cli','file':run_target.group(1),'args':flags,'exit':'zero',
                           'stdout':(printed or quoted).group(1),'evidence':run_target.group(0)+'; '+(printed or quoted).group(0)})
    route=re.search(r'(/[A-Za-z][\w/-]*)\s+returning\s+(\d{3})\b',request,re.I)
    if route and re.search(r'\bFlask\b',request,re.I):
        checks.append({'kind':'flask_http','file':entry,'path':route.group(1),'status':int(route.group(2)),'evidence':route.group(0)})
    port=re.search(r'\bport\s+(\d+)\b',request,re.I)
    if route and port and re.search(r'\bNode\b',request,re.I):
        checks.append({'kind':'node_http','file':entry,'path':route.group(1),'status':int(route.group(2)),'port':int(port.group(1)),'evidence':route.group(0)+'; '+port.group(0)})
    post=re.search(r'\bPOST\s+(/[A-Za-z][\w/-]*)',request,re.I)
    malformed=re.search(r'\bmalformed\s+JSON\b[^.!?]*\b(?:returns?|return)\s+(?:HTTP\s+)?(\d{3})',request,re.I)
    if post and malformed and (re.search(r'\bFlask\b',request,re.I) or (port and re.search(r'\bNode\b',request,re.I))):
        kind='flask_http' if re.search(r'\bFlask\b',request,re.I) else 'node_http'
        check={'kind':kind,'file':entry,'path':post.group(1),'method':'POST','body':'{broken',
               'status':int(malformed.group(1)),'invalid_input':True,'evidence':post.group(0)+'; '+malformed.group(0)}
        if kind=='node_http':check['port']=int(port.group(1))
        checks.append(check)
    preserve_all=bool(re.search(r'(?:existing|unrelated) files (?:unchanged|unmodified)|do not modify existing files',request,re.I))
    preserved={name:hashlib.sha256(data).hexdigest() for name,data in files.items()
        if preserve_all or re.search(r'\b(?:preserve|keep|leave)\s+'+re.escape(name)+r'\s+(?:byte.for.byte\s+)?unchanged\b',request,re.I)}
    language={'.py':'Python','.js':'Node','.mjs':'Node','.cjs':'Node','.java':'Java'}.get(PurePosixPath(entry).suffix,'')
    classes = {key: [] for key in REQUIREMENT_CLASSES}
    classes.update(FILE=required, INTERFACE=[c for c in checks if c['kind'].startswith('python_')],
                   NORMAL=[c for c in clauses if c not in errors and c not in persistence],
                   INVALID_INPUT=errors, ERROR=errors, OUTPUT=[c for c in clauses if re.search(r'print|output|return', c, re.I)],
                   PERSISTENCE=persistence, PRESERVATION=list(preserved), ENTRYPOINT=[entry] if entry else [], ACCEPTANCE=checks)
    return {'version':2,'original_request':request,'request_sha256':hashlib.sha256(request.encode()).hexdigest(),
        'requirement_classes':classes,
        'file_obligations':{path:[c for c in checks if c.get('file')==path] for path in generated},
        'deliverable':proposed.get('deliverable','edit'),'required_files':required,
        'language_framework':language,'entrypoint':entry,'arguments':flags,
        'outputs':[c['stdout'] for c in checks if 'stdout' in c],
        'error_behavior':errors,
        'interfaces':[c for c in checks if c['kind'] in {'python_return','python_exception'}],
        'persistence_requirements':persistence, 'preservation_rules':preserved,
        'acceptance_checks':checks,'planned_files':generated,
        'restrict_files':bool(re.search(r'(?:do not create|without creating) unrelated files',request,re.I)),
        'coverage':'literal obligations only; other behavior requires independent acceptance tests'}


def validator_script(contract):
    """Trusted template: no model-generated validator or shell command is evaluated."""
    return '''import os, sys, shutil, json, subprocess, importlib, hashlib, re, time, urllib.request, urllib.error
from pathlib import Path
contract=json.loads('''+repr(json.dumps(contract))+''')
root=Path('/output/project')
shutil.copytree('/input',root,ignore=lambda s,n:{'program.py'} if Path(s)==Path('/input') else set())
os.chdir(root);sys.path.insert(0,str(root))
records=[]
for name,digest in contract['preservation_rules'].items():
    actual=hashlib.sha256(Path(name).read_bytes()).hexdigest() if Path(name).is_file() else None
    records.append({'kind':'preservation','file':name,'passed':actual==digest,'expected':digest,'actual':actual})
for check in contract['acceptance_checks']:
    record={**check,'passed':False}
    try:
        target=check.get('file','')
        kind=check['kind']
        if kind=='file':
            assert Path(target).is_file() and Path(target).stat().st_size>0, 'Required nonempty file missing'
        elif kind=='python_return':
            module=importlib.import_module(target[:-3].replace('/','.'))
            actual=getattr(module,check['symbol'])()
            record['actual']=repr(actual)
            assert actual==check['expected'], 'Return value violates original request'
        elif kind=='python_exception':
            module=importlib.import_module(target[:-3].replace('/','.'))
            record['command']=['python-call',target,check['symbol']]
            record['input']={'args':check['args'],'kwargs':check['kwargs']}
            try:
                actual=getattr(module,check['symbol'])(*check['args'],**check['kwargs'])
            except Exception as exc:
                record['actual']=type(exc).__name__
                import builtins
                assert isinstance(exc,getattr(builtins,check['expected'])), 'Wrong exception type'
            else:
                record['actual']=repr(actual)[:500]
                raise AssertionError('Expected '+check['expected']+' but function returned')
        elif kind=='cli':
            suffix=Path(target).suffix
            if suffix=='.py': command=[sys.executable,target,*check['args']]
            elif suffix in ('.js','.mjs','.cjs'):command=['node',target,*check['args']]
            elif suffix=='.java':
                Path('/output/classes').mkdir(exist_ok=True)
                built=subprocess.run(['javac','-J-Xmx128m','-d','/output/classes',*list(map(str,Path('.').rglob('*.java')))],capture_output=True,text=True,timeout=25)
                assert built.returncode==0,built.stderr
                package=re.search(r'(?m)^\\s*package\\s+([\\w.]+)\\s*;',Path(target).read_text())
                classname=(package.group(1)+'.' if package else '')+Path(target).stem
                command=['java','-Xmx128m','-cp','/output/classes',classname,*check['args']]
            else:raise AssertionError('No CLI adapter for contract entrypoint')
            record['command']=command
            p=subprocess.run(command,input='',capture_output=True,text=True,timeout=10)
            record.update(exit_code=p.returncode,actual_stdout=p.stdout[-2000:],stderr=p.stderr[-2000:])
            if 'stdout' not in check:record['stdout']=p.stdout[-2000:]
            assert (p.returncode==0)==(check['exit']=='zero'), 'Unexpected CLI exit status'
            if 'stdout' in check:assert p.stdout.strip()==check['stdout'],'Unexpected CLI output'
            if check.get('error_required'):assert p.stderr.strip() or p.stdout.strip(),'Missing error message'
        elif kind=='flask_http':
            from flask import Flask
            module=importlib.import_module(target[:-3].replace('/','.'))
            apps=[v for v in vars(module).values() if isinstance(v,Flask)]
            if not apps and callable(getattr(module,'create_app',None)):
                app=module.create_app()
                if isinstance(app,Flask):apps=[app]
            assert len(apps)==1,'Expected one Flask application'
            record['input']={'method':check.get('method','GET'),'path':check['path'],'body':check.get('body')}
            record['command']=['flask-test-client',target,check.get('method','GET'),check['path']]
            response=apps[0].test_client().open(check['path'],method=check.get('method','GET'),data=check.get('body'),content_type='application/json' if 'body' in check else None)
            record['actual']=response.status_code
            assert response.status_code==check['status'],'HTTP status violates contract'
        elif kind=='node_http':
            command=['node',target];record['command']=command
            with open('/output/http.stdout','w+') as stdout,open('/output/http.stderr','w+') as stderr:
                process=subprocess.Popen(command,stdout=stdout,stderr=stderr)
                try:
                    actual=None
                    for attempt in range(40):
                        try:
                            record['input']={'method':check.get('method','GET'),'path':check['path'],'body':check.get('body')}
                            req=urllib.request.Request('http://127.0.0.1:'+str(check['port'])+check['path'],data=check['body'].encode() if 'body' in check else None,method=check.get('method','GET'),headers={'Content-Type':'application/json'} if 'body' in check else {})
                            with urllib.request.urlopen(req,timeout=.25) as response:actual=response.status
                            break
                        except urllib.error.HTTPError as exc:actual=exc.code;break
                        except (OSError,urllib.error.URLError):
                            if process.poll() is not None:break
                            time.sleep(.1)
                    record['actual']=actual
                    assert actual==check['status'],'HTTP readiness/status violates contract'
                finally:
                    if process.poll() is None:process.terminate()
                    try:process.wait(timeout=2)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
                    stdout.seek(0);stderr.seek(0)
                    record.update(stdout=stdout.read()[-2000:],stderr=stderr.read()[-2000:],exit_code=process.returncode)
        else:raise AssertionError('Unsupported independent contract criterion')
        record['passed']=True
    except Exception as exc:record['error']=type(exc).__name__+': '+str(exc)[:2000]
    records.append(record)
print('BUILD_CONTRACT_RESULT='+json.dumps(records))
sys.exit(0 if all(r['passed'] for r in records) else 1)
'''
