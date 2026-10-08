"""Bounded Flask requests executed only in the verified Docker sandbox."""
import hashlib
import json
import threading
from pathlib import Path
from backend.contracts import WorkbenchError

_LOCK = threading.Lock()


def preview_request(coding, sandbox, state_root, workspace_id, target, path='/', method='GET', body=None, files_snapshot=None):
    if files_snapshot is None:coding.read(workspace_id,target)
    else:coding._name(target)
    if files_snapshot is not None and target not in files_snapshot:raise WorkbenchError('invalid_file','Draft entrypoint unavailable')
    if not target.endswith('.py') or not all(part.isidentifier() for part in Path(target).with_suffix('').parts):
        raise WorkbenchError('unsupported_preview', 'Select a Python Flask entrypoint')
    if not isinstance(path, str) or not path.startswith('/') or path.startswith('//') or len(path)>2048:
        raise WorkbenchError('invalid_preview', 'Preview requests must use an application-relative path')
    if method not in {'GET','POST','PUT','PATCH','DELETE'} or len(json.dumps(body))>32768:
        raise WorkbenchError('invalid_preview', 'Preview request exceeds its method or body limit')
    with _LOCK:
        files=dict(files_snapshot) if files_snapshot is not None else coding.raw_files(workspace_id)
        revision=hashlib.sha256(b''.join(name.encode()+b'\0'+data for name,data in sorted(files.items()))).hexdigest()
        # One digest retains the full revision/entrypoint identity without two
        # nested 64-character components that exceed Windows path limits.
        entrypoint=hashlib.sha256(target.encode()).hexdigest()
        legacy=Path(state_root)/workspace_id/revision/entrypoint/'state.db'
        cache=Path(state_root)/workspace_id/hashlib.sha256((revision+'\0'+target).encode()).hexdigest()
        cache.mkdir(parents=True,exist_ok=True)
        database=cache/'state.db'
        if not database.exists() and legacy.exists():
            database.write_bytes(legacy.read_bytes())
        if database.exists():files['__preview_state__.db']=database.read_bytes()
        payload=json.dumps([target,path,method,body])
        script=r"""import sys,os,json,shutil,importlib,re
from pathlib import Path
root=Path('/output/project')
shutil.copytree('/input',root,ignore=lambda src,names:{'program.py'} if src=='/input' else set())
os.chdir(root);sys.path.insert(0,str(root))
target,path,method,body=json.loads(PAYLOAD)
module=importlib.import_module('.'.join(Path(target).with_suffix('').parts))
from flask import Flask
app=getattr(module,'app',None)
assert isinstance(app,Flask),'Entrypoint does not export a Flask app'
db=getattr(module,'db',None);dbpath=None
if db is not None:
    with app.app_context():
        assert db.engine.url.drivername=='sqlite','Preview supports only isolated SQLite databases'
        dbpath=Path(db.engine.url.database).resolve()
        assert dbpath.is_relative_to(Path('/output')),'Database must stay in the isolated output volume'
        dbpath.parent.mkdir(parents=True,exist_ok=True)
        if Path('/input/__preview_state__.db').exists():shutil.copyfile('/input/__preview_state__.db',dbpath)
        db.create_all()
client=app.test_client()
response=client.open(path,method=method,json=body if body is not None else None)
text=response.get_data(as_text=True)
if response.mimetype=='text/html':
    from urllib.parse import urljoin,urlsplit
    def local_asset(reference):
        if urlsplit(reference).scheme or reference.startswith('//'):return None
        return urljoin(path,reference)
    def stylesheet(match):
        href=local_asset(match.group(1))
        if href is None:return ''
        asset=client.get(href)
        return '<style>'+asset.get_data(as_text=True).replace('</style','<\\/style')+'</style>' if asset.status_code==200 else ''
    text=re.sub(r'''<link[^>]*href=["']([^"']+)["'][^>]*>''',stylesheet,text)
    def javascript(match):
        src=local_asset(match.group(1))
        if src is None:return ''
        asset=client.get(src)
        code=asset.get_data(as_text=True).replace('</script','<\\/script')
        if re.search(r'\bdefer\b',match.group(0),re.I):code="addEventListener('DOMContentLoaded',()=>{\n"+code+"\n});"
        return '<script>'+code+'</script>' if asset.status_code==200 else ''
    text=re.sub(r'''<script[^>]*src=["']([^"']+)["'][^>]*>\s*</script>''',javascript,text)
Path('/output/web-response.json').write_text(json.dumps({'status':response.status_code,'content_type':response.content_type,'body':text}))
if dbpath and dbpath.exists():
    with app.app_context():db.session.remove();db.engine.dispose()
    shutil.copyfile(dbpath,'/output/preview-state.db')
""".replace('PAYLOAD',repr(payload))
        from router.sandbox import CodeSandbox
        if isinstance(sandbox,CodeSandbox) and files_snapshot is None:
            # Keep app globals, cookies and SQLite state within one bounded
            # container instead of booting the project for every UI click.
            setup,request_code=script.split('response=client.open',1)
            request_code='response=client.open'+request_code
            request_code=request_code.split("if dbpath and dbpath.exists():",1)[0]
            request_code=request_code.replace("{'status':response.status_code", "{'request_id':command['request_id'],'status':response.status_code")
            request_code+="\nprint('SOVEREIGN_PREVIEW:'+json.dumps({'request_id':command['request_id'],'ready':True}),flush=True)"
            loop="\nfor line in sys.stdin:\n    command=json.loads(line)\n    if command.get('stop'):break\n    path,method,body=command['path'],command['method'],command.get('body')\n    try:\n"+'\n'.join('        '+line for line in request_code.splitlines())+"\n    except Exception as error:\n        print('SOVEREIGN_PREVIEW:'+json.dumps({'error':str(error)}),flush=True)\n"
            final="\nif dbpath and dbpath.exists():\n    with app.app_context():db.session.remove();db.engine.dispose()\n    shutil.copyfile(dbpath,'/output/preview-state.db')\n"
            from workflows.preview_session import session_request
            return session_request((str(state_root),workspace_id,revision,target),sandbox,setup+loop+final,files,database,{'path':path,'method':method,'body':body})
        result=sandbox.execute(script,timeout=30,input_files=files)
        if result.exit_code!=0:
            raise WorkbenchError('preview_failed',result.stderr[-4000:] or 'Docker preview failed')
        response=result.output_files.get('web-response.json')
        if response is None:raise WorkbenchError('preview_failed','Docker returned no bounded HTTP response')
        if 'preview-state.db' in result.output_files:
            database.write_bytes(result.output_files['preview-state.db'])
        return json.loads(response)
