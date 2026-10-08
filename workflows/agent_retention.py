"""Bounded, explicitly owned ephemeral cache. Never targets workspace/evidence roots."""
import json
import time
from pathlib import Path

class EphemeralRetention:
    def __init__(self,data_dir,max_bytes=64*1024*1024,max_age_days=7):
        self.root=Path(data_dir)/'agent-ephemeral'
        if self.root.is_symlink() or (hasattr(self.root,'is_junction') and self.root.is_junction()):raise ValueError('Linked ephemeral root')
        if self.root.is_dir() and any(self.root.iterdir()) and not (self.root/'ownership.json').is_file():raise ValueError('Existing directory is not an owned ephemeral cache')
        self.root.mkdir(parents=True,exist_ok=True)
        self.max_bytes=max_bytes;self.max_age=max_age_days*86400
        marker=self.root/'ownership.json'
        if marker.is_symlink():raise ValueError('Linked cache ownership marker')
        expected={'owner':'SovereignAI agent kernel','kind':'ephemeral cache','never_contains':'user workspaces, accepted artifacts, models or historical evidence'}
        if marker.exists() and json.loads(marker.read_text())!=expected:raise ValueError('Cache ownership mismatch')
        marker.write_text(json.dumps(expected,indent=2),encoding='utf-8')
    def prune(self,now=None):
        now=time.time() if now is None else now
        files=[]
        for path in self.root.glob('cache-*.json'):
            if path.is_symlink() or not path.is_file() or path.resolve().parent!=self.root.resolve():continue
            try:
                entry=json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(entry,dict) or entry.get('owner')!='sovereign-native-tool-log' or path.name!='cache-'+entry.get('key','')+'.json':continue
            except (OSError,ValueError,UnicodeError):continue
            files.append((path,path.stat().st_mtime,path.stat().st_size))
        total=sum(size for _,_,size in files);removed=[]
        for path,modified,size in sorted(files,key=lambda row:row[1]):
            if now-modified>self.max_age or total>self.max_bytes:
                path.unlink();total-=size;removed.append(path.name)
        return {'removed_owned_cache_files':removed,'retained_bytes':total,'max_bytes':self.max_bytes,'max_age_seconds':self.max_age}
    def write(self,key,payload):
        if not key.isalnum():raise ValueError('Cache key must be an application-generated identifier')
        path=self.root/('cache-'+key+'.json')
        temporary=path.with_suffix('.'+__import__('uuid').uuid4().hex+'.tmp')
        temporary.write_text(json.dumps({'owner':'sovereign-native-tool-log','key':key,'records':payload},ensure_ascii=False),encoding='utf-8')
        temporary.replace(path)
        self.prune()
        return str(path)
