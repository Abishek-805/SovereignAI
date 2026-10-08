"""Fixed entry-point commands, always executed by the Docker sandbox."""
import json
import ast
from pathlib import PurePosixPath

from backend.contracts import WorkbenchError

LANGUAGES = {'.py':'Python', '.js':'JavaScript', '.mjs':'JavaScript', '.cjs':'JavaScript',
             '.ts':'TypeScript', '.tsx':'TypeScript JSX', '.jsx':'JavaScript JSX', '.java':'Java', '.c':'C', '.cpp':'C++', '.cc':'C++',
             '.go':'Go', '.rs':'Rust', '.php':'PHP', '.sh':'Shell',
             '.sql':'SQL', '.cxx':'C++', '.bash':'Shell',
             '.html':'HTML', '.htm':'HTML', '.css':'CSS', '.json':'JSON', '.md':'Markdown', '.txt':'Text'}

def source_language(target):
    # Build manifests are editable artifacts, never permission to build/run a
    # user-selected container image instead of the pinned sandbox.
    if PurePosixPath(target).name=='Dockerfile':return 'Dockerfile'
    return LANGUAGES.get(PurePosixPath(target).suffix.lower())


def desktop_requirements(source):
    """Detect actual device/window calls, rather than guessing from filenames."""
    try: tree=ast.parse(source)
    except SyntaxError: return []
    requirements=set()
    for node in ast.walk(tree):
        if not isinstance(node,ast.Call): continue
        name=node.func.attr if isinstance(node.func,ast.Attribute) else node.func.id if isinstance(node.func,ast.Name) else ''
        if name=='VideoCapture' and (not node.args or isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,int)):
            requirements.add('camera')
        if name in {'imshow','namedWindow','Tk','mainloop'}: requirements.add('desktop window')
    return sorted(requirements)


def runner(target, mode='check', tests=False):
    suffix = PurePosixPath(target).suffix.lower()
    if PurePosixPath(target).name=='Dockerfile':
        if mode=='run':raise WorkbenchError('unsupported_language','User Dockerfiles are not executed; the approved sandbox image remains pinned.')
        suffix='.txt'
    if suffix not in LANGUAGES or mode not in {'check','run'}:
        raise WorkbenchError('unsupported_language', 'This file can be edited, but no local execution adapter is configured for it.')
    if mode == 'run' and suffix in {'.html', '.htm', '.css'}:
        raise WorkbenchError('preview_required', 'HTML uses the Preview button beside Save. CSS is rendered by an HTML page, not run as a standalone program.')
    # Input paths are validated by CodingWorkspace and CodeSandbox before this script runs.
    return '''import os, sys, subprocess, shutil, json, re
from pathlib import Path
target, suffix, mode, tests = json.loads(''' + repr(json.dumps([target,suffix,mode,tests])) + ''')
root = Path('/output/project')
# Only the sandbox's root wrapper is reserved. A project dependency named
# program.py inside a package is user data and must be copied with its package.
shutil.copytree('/input', root, ignore=lambda source, names: {'program.py'} if Path(source) == Path('/input') else set())
os.chdir(root)
os.environ.update(HOME='/output', TMPDIR='/output', GOCACHE='/output/go-cache', GOTOOLCHAIN='local', GOPROXY='off', GOSUMDB='off')
def command(args):
    completed = subprocess.run(args, timeout=110 if run else 25)
    if completed.returncode: sys.exit(completed.returncode)
run = mode == 'run'
if suffix == '.py':
    if tests:
        sys.path.insert(0,str(root))
        import unittest
        class DiagnosticResult(unittest.TextTestResult):
            def report_inputs(self,test,error):
                import ast
                frames=[];affected=set()
                trace=error[2]
                while trace:
                    frame=trace.tb_frame;name=frame.f_code.co_filename
                    if name.startswith(str(root)) and Path(name).name.startswith('test_'):
                        values={}
                        for key,value in frame.f_locals.items():
                            if isinstance(value,subprocess.CompletedProcess):
                                # Assertions on a child process otherwise lose
                                # the invocation and actual output before repair.
                                if len(values)>=6:continue
                                args=value.args
                                args=([str(arg)[:200] for arg in args[:20]]
                                    if isinstance(args,(list,tuple)) else str(args)[:1000])
                                values[key]={'args':args,'returncode':value.returncode,
                                    'stdout':str(value.stdout or '')[-1000:],
                                    'stderr':str(value.stderr or '')[-1000:]}
                                continue
                            if key=='self' or not isinstance(value,(str,int,float,bool,list,tuple,dict,type(None))):continue
                            try:
                                encoded=json.dumps(value,ensure_ascii=True)
                                if len(encoded)<=240 and len(values)<6:values[key]=value
                            except (TypeError,ValueError):pass
                        try:source=Path(name).read_text().splitlines()
                        except OSError:source=[]
                        excerpt='\\n'.join(source[max(0,trace.tb_lineno-4):trace.tb_lineno+1])[:1500]
                        frames.append({'file':str(Path(name).relative_to(root)),'line':trace.tb_lineno,
                            'observed_inputs':values,'assertion_context':excerpt})
                        try:
                            tree=ast.parse(Path(name).read_text())
                            for node in ast.walk(tree):
                                if isinstance(node,ast.ImportFrom) and node.module:
                                    candidate=node.module.replace('.','/')+'.py'
                                    if Path(candidate).is_file():affected.add(candidate)
                                if isinstance(node,ast.Constant) and isinstance(node.value,str) and node.value.endswith('.py') and Path(node.value).is_file():affected.add(node.value)
                        except (OSError,SyntaxError):pass
                    trace=trace.tb_next
                self.stream.writeln('INDEPENDENT_TEST_FAILURE='+json.dumps({'kind':'independent_test','test':test.id(),
                    'passed':False,'frames':frames[-2:],'affected_files':sorted(affected),'error':str(error[1])[:500]},ensure_ascii=True))
            def addFailure(self,test,error):
                super().addFailure(test,error);self.report_inputs(test,error)
            def addError(self,test,error):
                super().addError(test,error);self.report_inputs(test,error)
        suite = unittest.defaultTestLoader.discover(str(root), pattern='test_*.py')
        result = unittest.TextTestRunner(verbosity=2,resultclass=DiagnosticResult).run(suite)
        sys.exit(0 if result.testsRun and result.wasSuccessful() else 1)
    if run:
        path=Path(target)
        os.environ['PYTHONPATH']=str(root)+os.pathsep+str(root/path.parent)
        parts=path.with_suffix('').parts
        command(['python','-m','.'.join(parts)] if len(parts)>1 and all(part.isidentifier() for part in parts) else ['python',target])
    else: compile(Path(target).read_text(), target, 'exec')
elif suffix in ('.js','.mjs','.cjs'):
    command(['node', target] if run else ['node','--check',target])
elif suffix in ('.jsx','.tsx'):
    if run:
        print('BLOCKED: JSX/TSX requires the project React/Vite build dependencies. Use the project package build command.',file=sys.stderr)
        sys.exit(78)
    package_root=subprocess.check_output(['npm','root','-g'],text=True).strip()
    checker="const fs=require('fs'),ts=require(process.argv[1]+'/typescript'); const source=fs.readFileSync(process.argv[2],'utf8'); const result=ts.transpileModule(source,{fileName:process.argv[2],reportDiagnostics:true,compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2020}}); const errors=(result.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error); for(const d of errors) console.error(ts.flattenDiagnosticMessageText(d.messageText,' ')); process.exit(errors.length?1:0);"
    command(['node','-e',checker,package_root,target])
elif suffix == '.ts':
    command(['tsc',target,'--target','es2020','--module','commonjs','--skipLibCheck','--rootDir','.','--outDir','/output/ts-build'])
    if run: command(['node', '/output/ts-build/'+str(Path(target).with_suffix('.js'))])
elif suffix == '.java':
    Path('/output/classes').mkdir()
    command(['javac','-J-Xmx128m','-sourcepath',str(root)+os.pathsep+str(root/Path(target).parent),'-d','/output/classes',target])
    package=re.search(r'(?m)^\\s*package\\s+([\\w.]+)\\s*;',Path(target).read_text())
    classname=(package.group(1)+'.' if package else '')+Path(target).stem
    if run: command(['java','-Xmx128m','-XX:ReservedCodeCacheSize=32m','-XX:CompressedClassSpaceSize=32m','-cp','/output/classes',classname])
elif suffix in ('.c','.cpp','.cc','.cxx'):
    compiler = 'gcc' if suffix == '.c' else 'g++'
    command([compiler,target,'-o','/output/app'] if run else [compiler,'-fsyntax-only',target])
    if run: command(['/output/app'])
elif suffix == '.go':
    os.environ['GOCACHE']='/opt/go-cache'
    if not Path('go.mod').exists():os.environ['GO111MODULE']='off'
    command(['go','build','-o','/output/app','./'+str(Path(target).parent)])
    if run: command(['/output/app'])
elif suffix == '.rs':
    command(['rustc',target,'-o','/output/app'])
    if run: command(['/output/app'])
elif suffix == '.php': command(['php',target] if run else ['php','-l',target])
elif suffix in ('.sh','.bash'): command(['bash',target] if run else ['bash','-n',target])
elif suffix == '.sql':
    import sqlite3
    db = sqlite3.connect(':memory:')
    db.executescript(Path(target).read_text())
elif suffix == '.json': json.loads(Path(target).read_text())
else: Path(target).read_text(encoding='utf-8')
print('Execution finished.' if run else 'Check passed. This does not prove functional correctness.')
'''


def http_runner(target, path, port):
    """Probe a bounded Node HTTP process entirely inside its Docker container."""
    if not isinstance(port,int) or not 1<=port<=65535 or not isinstance(path,str) or not path.startswith('/') or path.startswith('//'):
        raise WorkbenchError('invalid_preview','Invalid local HTTP probe')
    payload=repr(json.dumps([target,path,port]))
    return """import os,sys,subprocess,shutil,json,time,urllib.request
from pathlib import Path
target,path,port=json.loads(PAYLOAD)
root=Path('/output/project')
shutil.copytree('/input',root,ignore=lambda src,names:{'program.py'} if src=='/input' else set())
os.chdir(root)
log=open('/output/http-process.log','w+')
proc=subprocess.Popen(['node',target],stdout=log,stderr=log,env={**os.environ,'PORT':str(port)})
try:
    for attempt in range(50):
        if proc.poll() is not None:
            log.flush();log.seek(0);raise RuntimeError(log.read()[-4000:] or 'HTTP process exited before readiness')
        try:
            with urllib.request.urlopen('http://127.0.0.1:'+str(port)+path,timeout=1) as response:
                result={'status':response.status,'body':response.read(32768).decode('utf-8',errors='replace')}
            Path('/output/http-response.json').write_text(json.dumps(result))
            print('Node application served HTTP '+str(result['status'])+' '+path)
            if result['status']!=200:sys.exit(1)
            break
        except urllib.error.HTTPError as error:raise RuntimeError('HTTP '+str(error.code)+' '+path) from error
        except (OSError,TimeoutError):time.sleep(.1)
    else:raise RuntimeError('HTTP process did not become ready in five seconds')
finally:
    proc.terminate()
    try:proc.wait(timeout=2)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()
    log.close()
""".replace('PAYLOAD',payload)
