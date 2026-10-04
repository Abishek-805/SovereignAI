"""Bounded Flask requests executed only in the verified Docker sandbox."""
import hashlib
import json
import threading
from pathlib import Path
from backend.contracts import WorkbenchError

_LOCK = threading.Lock()


def preview_request(coding, sandbox, state_root, workspace_id, target, path='/', method='GET', body=None):
    coding.read(workspace_id, target)  # Validate the selected workspace path.
    if not target.endswith('.py') or not all(part.isidentifier() for part in Path(target).with_suffix('').parts):
        raise WorkbenchError('unsupported_preview', 'Select a Python Flask entrypoint')
    if not isinstance(path, str) or not path.startswith('/') or path.startswith('//') or len(path)>2048:
        raise WorkbenchError('invalid_preview', 'Preview requests must use an application-relative path')
    if method not in {'GET','POST','PUT','PATCH','DELETE'} or len(json.dumps(body))>32768:
        raise WorkbenchError('invalid_preview', 'Preview request exceeds its method or body limit')
    with _LOCK:
        files=coding.raw_files(workspace_id)
        revision=hashlib.sha256(b''.join(name.encode()+b'\0'+data for name,data in sorted(files.items()))).hexdigest()
        cache=Path(state_root)/workspace_id/revision
        cache.mkdir(parents=True,exist_ok=True)
        database=cache/'state.db'
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
    def stylesheet(match):
        href=match.group(1)
        if not href.startswith('/') or href.startswith('//'):return ''
        asset=client.get(href)
        return '<style>'+asset.get_data(as_text=True).replace('</style','<\\/style')+'</style>' if asset.status_code==200 else ''
    text=re.sub(r'''<link[^>]*href=["']([^"']+)["'][^>]*>''',stylesheet,text)
Path('/output/web-response.json').write_text(json.dumps({'status':response.status_code,'content_type':response.content_type,'body':text}))
if dbpath and dbpath.exists():
    with app.app_context():db.session.remove();db.engine.dispose()
    shutil.copyfile(dbpath,'/output/preview-state.db')
""".replace('PAYLOAD',repr(payload))
        result=sandbox.execute(script,timeout=30,input_files=files)
        if result.exit_code!=0:
            raise WorkbenchError('preview_failed',result.stderr[-4000:] or 'Docker preview failed')
        response=result.output_files.get('web-response.json')
        if response is None:raise WorkbenchError('preview_failed','Docker returned no bounded HTTP response')
        if 'preview-state.db' in result.output_files:
            database.write_bytes(result.output_files['preview-state.db'])
        return json.loads(response)
