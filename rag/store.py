from contextlib import contextmanager
from pathlib import Path
import json
import hashlib
from uuid import uuid4
from dataclasses import replace
import sqlite3
import numpy as np
from backend.contracts import Chunk, WorkbenchError

SCHEMA = '''
CREATE TABLE IF NOT EXISTS documents(document_id TEXT PRIMARY KEY, display_name TEXT NOT NULL, source_path TEXT NOT NULL, active_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS versions(document_id TEXT NOT NULL, version_hash TEXT NOT NULL, embedding_revision TEXT NOT NULL, warnings_json TEXT NOT NULL, PRIMARY KEY(document_id,version_hash));
CREATE TABLE IF NOT EXISTS chunks(chunk_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, version_hash TEXT NOT NULL, payload TEXT NOT NULL, text TEXT NOT NULL, vector BLOB NOT NULL, FOREIGN KEY(document_id,version_hash) REFERENCES versions(document_id,version_hash));
CREATE TABLE IF NOT EXISTS document_folders(document_id TEXT PRIMARY KEY REFERENCES documents(document_id) ON DELETE CASCADE, folder TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pending_imports(document_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS chunk_version ON chunks(document_id,version_hash);
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(chunk_id UNINDEXED,text);
'''
ACTIVE = ' FROM chunks c JOIN documents d ON c.document_id=d.document_id AND c.version_hash=d.active_hash '


class Store:
    def __init__(self, db_path, max_chunks=20000):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_chunks = max_chunks
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript(SCHEMA)
            for row in db.execute('SELECT * FROM pending_imports').fetchall():
                payload=json.loads(row['payload'])
                if payload.get('indexing_status')=='indexing':
                    payload.update(indexing_status='failed',indexing_error='Indexing was interrupted. Original retained; reimport to resume.')
                    db.execute('UPDATE pending_imports SET payload=? WHERE document_id=?',(json.dumps(payload),row['document_id']))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def documents(self):
        with self.connect() as db:
            rows = db.execute('''SELECT d.document_id,d.display_name,d.source_path,d.active_hash,COALESCE((SELECT folder FROM document_folders f WHERE f.document_id=d.document_id),'') AS folder,v.embedding_revision,v.warnings_json,
                (SELECT count(*) FROM chunks c WHERE c.document_id=d.document_id AND c.version_hash=d.active_hash) AS chunk_count
                FROM documents d JOIN versions v ON d.document_id=v.document_id AND d.active_hash=v.version_hash ORDER BY d.document_id''').fetchall()
            pending={r['document_id']:json.loads(r['payload']) for r in db.execute('SELECT * FROM pending_imports')}
        result=[{**{k:r[k] for k in r.keys() if k not in {'warnings_json','source_path'}}, 'source_extension':Path(r['source_path']).suffix.lower(), 'warnings':json.loads(r['warnings_json']), 'indexing_status':'indexed'} for r in rows]
        for doc in result:
            if doc['document_id'] in pending: doc['indexing_status']=pending.pop(doc['document_id'])['indexing_status']
        return result+list(pending.values())

    def register_import(self, document_id, name, digest, suffix):
        payload={'document_id':document_id,'display_name':name,'active_hash':digest,'source_extension':suffix,
                 'chunk_count':0,'warnings':[],'embedding_revision':None,'indexing_status':'indexing'}
        with self.connect() as db:
            db.execute('INSERT INTO pending_imports VALUES(?,?) ON CONFLICT(document_id) DO UPDATE SET payload=excluded.payload',(document_id,json.dumps(payload)))
        return payload

    def import_status(self, document_id, status, error=''):
        with self.connect() as db:
            row=db.execute('SELECT payload FROM pending_imports WHERE document_id=?',(document_id,)).fetchone()
            if row:
                payload=json.loads(row[0]); payload.update(indexing_status=status,indexing_error=error)
                db.execute('UPDATE pending_imports SET payload=? WHERE document_id=?',(json.dumps(payload),document_id))

    def current(self, document_id):
        return next((d for d in self.documents() if d['document_id']==document_id), None)

    def exact_duplicates(self, remove=False):
        """Group exact indexed source SHA256s; delete surplus entries atomically.

        Extracted text, similar names and different source versions are never
        duplicate evidence. Source files are untouched. Stable ID ordering keeps
        a deterministic original, preferring an entry without a copy suffix.
        """
        with self.connect() as db:
            if remove:
                db.execute('BEGIN IMMEDIATE')
            rows=db.execute('SELECT document_id,display_name,active_hash FROM documents ORDER BY document_id').fetchall()
            hashes={}
            for row in rows:
                digest=row['active_hash']
                if len(digest)==64 and all(c in '0123456789abcdef' for c in digest):
                    hashes.setdefault(digest,[]).append(dict(row))
            groups=[]
            for digest, members in sorted(hashes.items()):
                if len(members)<2:continue
                members.sort(key=lambda item: (' (copy)' in Path(item['display_name']).stem.casefold(),item['document_id']))
                keep,duplicates=members[0],members[1:]
                groups.append({'source_hash':digest,'kept':keep,'duplicates':duplicates})
            # Fail before writes if the audit cannot fit the tool output budget.
            if len(json.dumps(groups).encode('utf-8'))>160000:
                raise WorkbenchError('resource_limit','Duplicate audit exceeds its budget; manage named documents individually')
            for group in groups if remove else []:
                for doc in group['duplicates']:
                    self.check_version(db,doc['document_id'],doc['active_hash'])
                    identity=doc['document_id']
                    db.execute('DELETE FROM chunk_fts WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE document_id=?)',(identity,))
                    db.execute('DELETE FROM chunks WHERE document_id=?',(identity,))
                    db.execute('DELETE FROM versions WHERE document_id=?',(identity,))
                    db.execute('DELETE FROM documents WHERE document_id=?',(identity,))
            count=sum(len(group['duplicates']) for group in groups)
        return {'groups':groups,'duplicate_count':count,'removed_count':count if remove else 0,'source_files_preserved':True}

    def rename_document(self, document_id, display_name, expected_hash=None):
        name = display_name.strip()
        if not name or len(name) > 255 or (any(ch in name for ch in '/\\:\x00') or any(ord(ch)<32 for ch in name)) or name in {'.', '..'}:
            raise WorkbenchError('invalid_filename', 'Use a simple document name without directories')
        with self.connect() as db:
            pending=db.execute('SELECT payload FROM pending_imports WHERE document_id=?',(document_id,)).fetchone()
            if pending and not db.execute('SELECT 1 FROM documents WHERE document_id=?',(document_id,)).fetchone():
                payload=json.loads(pending[0])
                if expected_hash and payload['active_hash']!=expected_hash: raise WorkbenchError('document_conflict','Document changed')
                payload['display_name']=name
                db.execute('UPDATE pending_imports SET payload=? WHERE document_id=?',(json.dumps(payload),document_id))
                return payload
            self.check_version(db,document_id,expected_hash)
            changed = db.execute('UPDATE documents SET display_name=? WHERE document_id=?', (name, document_id)).rowcount
            if changed:
                for row in db.execute('SELECT chunk_id,payload FROM chunks WHERE document_id=?', (document_id,)).fetchall():
                    payload = json.loads(row['payload'])
                    payload['display_name'] = name
                    db.execute('UPDATE chunks SET payload=? WHERE chunk_id=?', (json.dumps(payload), row['chunk_id']))
        if not changed:
            raise WorkbenchError('unknown_document', 'Document does not exist')
        return self.current(document_id)

    def remove_document(self, document_id, expected_hash=None):
        with self.connect() as db:
            pending=db.execute('SELECT payload FROM pending_imports WHERE document_id=?',(document_id,)).fetchone()
            if pending and not db.execute('SELECT 1 FROM documents WHERE document_id=?',(document_id,)).fetchone():
                if expected_hash and json.loads(pending[0])['active_hash']!=expected_hash:
                    raise WorkbenchError('document_conflict','Document changed')
                db.execute('DELETE FROM pending_imports WHERE document_id=?',(document_id,))
                return {'document_id':document_id,'removed':True}
            self.check_version(db,document_id,expected_hash)
            if db.execute('SELECT 1 FROM documents WHERE document_id=?', (document_id,)).fetchone() is None:
                raise WorkbenchError('unknown_document', 'Document does not exist')
            db.execute('DELETE FROM chunk_fts WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE document_id=?)', (document_id,))
            db.execute('DELETE FROM chunks WHERE document_id=?', (document_id,))
            db.execute('DELETE FROM versions WHERE document_id=?', (document_id,))
            db.execute('DELETE FROM documents WHERE document_id=?', (document_id,))
            db.execute('DELETE FROM pending_imports WHERE document_id=?', (document_id,))
        return {'document_id': document_id, 'removed': True}

    def check_version(self, db, document_id, expected_hash=None):
        row=db.execute('SELECT active_hash FROM documents WHERE document_id=?',(document_id,)).fetchone()
        if row is None: raise WorkbenchError('unknown_document','Document does not exist')
        if expected_hash is not None and row[0]!=expected_hash:
            raise WorkbenchError('document_conflict','Document changed. Refresh the library before trying again.')

    def move_document(self, document_id, folder, expected_hash=None):
        folder=folder.strip()
        parts=folder.split('/') if folder else []
        if len(folder)>240 or any(part in {'','.', '..'} or any(ch in part for ch in '\\:\x00') or any(ord(ch)<32 for ch in part) for part in parts):
            raise WorkbenchError('invalid_folder','Use folder names separated by / without parent directories or special characters')
        with self.connect() as db:
            self.check_version(db,document_id,expected_hash)
            db.execute('INSERT INTO document_folders VALUES(?,?) ON CONFLICT(document_id) DO UPDATE SET folder=excluded.folder',(document_id,folder))
        return self.current(document_id)

    def copy_document(self, document_id, folder=None, expected_hash=None):
        with self.connect() as db:
            self.check_version(db,document_id,expected_hash)
            source_path=db.execute('SELECT source_path FROM documents WHERE document_id=?',(document_id,)).fetchone()[0]
        current=self.current(document_id)
        chunks=self.active_chunks([document_id])
        identity=hashlib.sha256(uuid4().bytes).hexdigest()
        name=Path(current['display_name'])
        suffix=name.suffix
        display_name=name.stem[:max(1,248-len(suffix))]+' (copy)'+suffix
        duplicated=[replace(chunk,document_id=identity,display_name=display_name,chunk_id=hashlib.sha256((identity+':'+chunk.chunk_id).encode()).hexdigest()) for chunk,_ in chunks]
        result=self.publish(identity,display_name,source_path,current['active_hash'],duplicated,[vector for _,vector in chunks],current['embedding_revision'],current['warnings'])
        try:
            result=self.move_document(identity,current['folder'] if folder is None else folder,result['active_hash'])
        except WorkbenchError:
            self.remove_document(identity)
            raise
        return {**result,'copied_from':document_id}

    def _scope(self, db, document_ids):
        if document_ids is None:
            return '', []
        if not document_ids:
            return ' AND 0 ', []
        ids = sorted(set(document_ids))
        placeholders = ','.join('?' for _ in ids)
        known = {r[0] for r in db.execute(f'SELECT document_id FROM documents WHERE document_id IN ({placeholders})', ids)}
        known.update(r[0] for r in db.execute(f'SELECT document_id FROM pending_imports WHERE document_id IN ({placeholders})',ids))
        if known != set(ids):
            raise WorkbenchError('unknown_document', 'Selected document does not exist')
        return f' AND d.document_id IN ({placeholders}) ', ids

    def publish(self, document_id, display_name, source_path, source_hash, chunks, vectors, embedding_revision, warnings):
        vectors = np.asarray(vectors, dtype='<f4')
        norms=np.linalg.norm(vectors,axis=1) if vectors.ndim==2 else np.array([])
        expected=np.array([0 if c.retrieval_kind=='lexical' else 1 for c in chunks])
        valid = (len(chunks)>0 and vectors.shape==(len(chunks),384) and np.isfinite(vectors).all()
                 and all(c.retrieval_kind in {'dense','schema','lexical'} for c in chunks)
                 and np.allclose(norms,expected,atol=1e-3)
                 and len({c.chunk_id for c in chunks})==len(chunks)
                 and all(c.document_id==document_id and c.version_hash==source_hash for c in chunks))
        if not valid:
            raise WorkbenchError('invalid_index', 'Chunk identity or embedding validation failed')
        try:
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                revisions = {r[0] for r in db.execute('SELECT DISTINCT v.embedding_revision FROM versions v JOIN documents d ON v.document_id=d.document_id AND v.version_hash=d.active_hash')}
                if revisions and revisions!={embedding_revision}:
                    raise WorkbenchError('embedding_mismatch','Collection uses a different embedding revision')
                old = db.execute('SELECT active_hash FROM documents WHERE document_id=?',(document_id,)).fetchone()
                if old and old[0]==source_hash:
                    status='unchanged'
                else:
                    count = db.execute('SELECT count(*)'+ACTIVE+'WHERE d.document_id<>?',(document_id,)).fetchone()[0]
                    if count+len(chunks)>self.max_chunks:
                        raise WorkbenchError('collection_limit','Active chunk limit exceeded')
                    version = db.execute('SELECT embedding_revision FROM versions WHERE document_id=? AND version_hash=?',(document_id,source_hash)).fetchone()
                    if version and version[0]!=embedding_revision:
                        raise WorkbenchError('embedding_mismatch','Historical version uses a different embedding revision')
                    if not version:
                        db.execute('INSERT INTO versions VALUES(?,?,?,?)',(document_id,source_hash,embedding_revision,json.dumps(warnings)))
                        for chunk,vector in zip(chunks,vectors):
                            db.execute('INSERT INTO chunks VALUES(?,?,?,?,?,?)',(chunk.chunk_id,document_id,source_hash,json.dumps(chunk.to_dict()),chunk.text,vector.tobytes()))
                            db.execute('INSERT INTO chunk_fts VALUES(?,?)',(chunk.chunk_id,chunk.text))
                    db.execute('INSERT INTO documents VALUES(?,?,?,?) ON CONFLICT(document_id) DO UPDATE SET display_name=excluded.display_name,source_path=excluded.source_path,active_hash=excluded.active_hash',
                               (document_id,display_name,source_path,source_hash))
                    status='replaced' if old else 'indexed'
                db.execute('DELETE FROM pending_imports WHERE document_id=?',(document_id,))
        except sqlite3.Error as exc:
            raise WorkbenchError('index_failed','Index update failed; previous active version retained') from exc
        return {'status':status, **self.current(document_id)}

    def planning_context(self, document_ids=None, query='', max_documents=8, total_chars=6000):
        """Bounded active-source previews for routing, never final evidence.

        Reads text only: no vector decoding, embeddings, original-file parsing,
        or instructions from the source are executed here.
        """
        if (isinstance(max_documents,bool) or not isinstance(max_documents,int) or
                not 1<=max_documents<=8 or isinstance(total_chars,bool) or
                not isinstance(total_chars,int) or not 1<=total_chars<=6000 or
                not isinstance(query,str)):
            raise WorkbenchError('invalid_request','Invalid planning context limits')
        from rag.retrieve import fts_query
        terms=fts_query(query[:8000])
        result=[]
        with self.connect() as db:
            scope,args=self._scope(db,document_ids)
            documents=db.execute('SELECT d.document_id,d.display_name FROM documents d WHERE 1 '+
                                 scope+' ORDER BY d.document_id LIMIT ?',[*args,max_documents]).fetchall()
            remaining=total_chars
            for position,document in enumerate(documents):
                if not remaining:break
                allowance=max(1,remaining//(len(documents)-position))
                # Prefer the imported schema overview; otherwise source order.
                # Chunk hashes deliberately do not determine preview order.
                first=db.execute('SELECT c.chunk_id,substr(c.text,1,?) AS text'+ACTIVE+
                    "WHERE d.document_id=? ORDER BY CASE WHEN json_extract(c.payload,'$.retrieval_kind')='schema' THEN 0 ELSE 1 END, "+
                    "COALESCE(json_extract(c.payload,'$.page'),0),COALESCE(json_extract(c.payload,'$.line_start'),0),c.rowid LIMIT 1",
                    (allowance,document['document_id'])).fetchone()
                if first is None:continue
                excerpt=first['text']
                if terms:
                    match=db.execute('SELECT c.chunk_id,substr(c.text,1,?) AS text FROM chunk_fts '+
                        'JOIN chunks c ON c.chunk_id=chunk_fts.chunk_id JOIN documents d '+
                        'ON d.document_id=c.document_id AND d.active_hash=c.version_hash '+
                        'WHERE chunk_fts MATCH ? AND d.document_id=? ORDER BY bm25(chunk_fts),c.rowid LIMIT 1',
                        (allowance,terms,document['document_id'])).fetchone()
                    if match is not None and match['chunk_id']!=first['chunk_id'] and match['text']!=excerpt:
                        base=max(1,allowance*2//3)
                        excerpt=(excerpt[:base]+'\n'+match['text'][:max(0,allowance-base-1)])[:allowance]
                excerpt=excerpt[:allowance]
                remaining-=len(excerpt)
                result.append({'document_id':document['document_id'],'name':document['display_name'],
                               'reference_excerpt':excerpt})
        return result

    def active_chunks(self, document_ids=None):
        with self.connect() as db:
            scope, args = self._scope(db,document_ids)
            rows=db.execute('SELECT c.payload,c.vector'+ACTIVE+'WHERE 1 '+scope+' ORDER BY c.chunk_id',args).fetchall()
        result=[]
        for row in rows:
            vector=np.frombuffer(row['vector'],dtype='<f4')
            if vector.shape!=(384,) or not np.isfinite(vector).all():
                raise WorkbenchError('invalid_index','Stored vector is invalid; rebuild the affected index')
            result.append((Chunk(**json.loads(row['payload'])),vector))
        return result

    def lexical(self, query, limit=12, document_ids=None):
        with self.connect() as db:
            scope,args=self._scope(db,document_ids)
            if not query:
                return []
            rows=db.execute('SELECT c.chunk_id FROM chunk_fts JOIN chunks c ON c.chunk_id=chunk_fts.chunk_id JOIN documents d ON d.document_id=c.document_id AND d.active_hash=c.version_hash WHERE chunk_fts MATCH ?'+scope+' ORDER BY bm25(chunk_fts),c.chunk_id LIMIT ?', [query,*args,limit]).fetchall()
        return [r[0] for r in rows]

    def get_chunk(self, chunk_id):
        with self.connect() as db:
            row=db.execute('SELECT payload FROM chunks WHERE chunk_id=?',(chunk_id,)).fetchone()
        if row is None:
            raise WorkbenchError('unknown_source','Source chunk does not exist')
        return Chunk(**json.loads(row[0]))
