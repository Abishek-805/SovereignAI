from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
import numpy as np
from backend.contracts import Chunk, WorkbenchError

SCHEMA = '''
CREATE TABLE IF NOT EXISTS documents(document_id TEXT PRIMARY KEY, display_name TEXT NOT NULL, source_path TEXT NOT NULL, active_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS versions(document_id TEXT NOT NULL, version_hash TEXT NOT NULL, embedding_revision TEXT NOT NULL, warnings_json TEXT NOT NULL, PRIMARY KEY(document_id,version_hash));
CREATE TABLE IF NOT EXISTS chunks(chunk_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, version_hash TEXT NOT NULL, payload TEXT NOT NULL, text TEXT NOT NULL, vector BLOB NOT NULL, FOREIGN KEY(document_id,version_hash) REFERENCES versions(document_id,version_hash));
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
            db.executescript(SCHEMA)

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
            rows = db.execute('''SELECT d.document_id,d.display_name,d.active_hash,v.embedding_revision,v.warnings_json,
                (SELECT count(*) FROM chunks c WHERE c.document_id=d.document_id AND c.version_hash=d.active_hash) AS chunk_count
                FROM documents d JOIN versions v ON d.document_id=v.document_id AND d.active_hash=v.version_hash ORDER BY d.document_id''').fetchall()
        return [{**{k:r[k] for k in r.keys() if k!='warnings_json'}, 'warnings':json.loads(r['warnings_json'])} for r in rows]

    def current(self, document_id):
        return next((d for d in self.documents() if d['document_id']==document_id), None)

    def rename_document(self, document_id, display_name):
        name = display_name.strip()
        if not name or len(name) > 255 or any(ch in name for ch in '/\\:\x00') or name in {'.', '..'}:
            raise WorkbenchError('invalid_filename', 'Use a simple document name without directories')
        with self.connect() as db:
            changed = db.execute('UPDATE documents SET display_name=? WHERE document_id=?', (name, document_id)).rowcount
            if changed:
                for row in db.execute('SELECT chunk_id,payload FROM chunks WHERE document_id=?', (document_id,)).fetchall():
                    payload = json.loads(row['payload'])
                    payload['display_name'] = name
                    db.execute('UPDATE chunks SET payload=? WHERE chunk_id=?', (json.dumps(payload), row['chunk_id']))
        if not changed:
            raise WorkbenchError('unknown_document', 'Document does not exist')
        return self.current(document_id)

    def remove_document(self, document_id):
        with self.connect() as db:
            if db.execute('SELECT 1 FROM documents WHERE document_id=?', (document_id,)).fetchone() is None:
                raise WorkbenchError('unknown_document', 'Document does not exist')
            db.execute('DELETE FROM chunk_fts WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE document_id=?)', (document_id,))
            db.execute('DELETE FROM chunks WHERE document_id=?', (document_id,))
            db.execute('DELETE FROM versions WHERE document_id=?', (document_id,))
            db.execute('DELETE FROM documents WHERE document_id=?', (document_id,))
        return {'document_id': document_id, 'removed': True}

    def _scope(self, db, document_ids):
        if document_ids is None:
            return '', []
        if not document_ids:
            return ' AND 0 ', []
        ids = sorted(set(document_ids))
        placeholders = ','.join('?' for _ in ids)
        known = {r[0] for r in db.execute(f'SELECT document_id FROM documents WHERE document_id IN ({placeholders})', ids)}
        if known != set(ids):
            raise WorkbenchError('unknown_document', 'Selected document does not exist')
        return f' AND d.document_id IN ({placeholders}) ', ids

    def publish(self, document_id, display_name, source_path, source_hash, chunks, vectors, embedding_revision, warnings):
        vectors = np.asarray(vectors, dtype='<f4')
        valid = (len(chunks)>0 and vectors.shape==(len(chunks),384) and np.isfinite(vectors).all()
                 and np.allclose(np.linalg.norm(vectors,axis=1),1,atol=1e-3)
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
        except sqlite3.Error as exc:
            raise WorkbenchError('index_failed','Index update failed; previous active version retained') from exc
        return {'status':status, **self.current(document_id)}

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
