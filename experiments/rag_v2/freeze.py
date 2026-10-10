"""Freeze existing public RAG fixtures without running their historical harnesses."""
import ast, hashlib, json, shutil
from pathlib import Path
from backend.contracts import Page, Extraction
from rag.ingest import extract, chunk_pages
from rag.embedding import Embedder

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence/rag-v2-comparison/20261009'

def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def literal(path,name):
    tree=ast.parse(path.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets):
            # The existing long fixture uses range/join; execute only this trusted assignment.
            scope={}
            exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),{'__builtins__':{'range':range}},scope)
            return scope[name]
    raise ValueError(name)

def main():
    OUT.mkdir(parents=True,exist_ok=False)
    (OUT/'fixtures').mkdir()
    texts=literal(ROOT/'benchmarks/rag_integration.py','texts')
    cases=literal(ROOT/'benchmarks/rag_integration.py','cases')
    texts['pdf']='Synthetic manual cover\n\nPump P-404 inspection interval is 30 days.'
    # Preserve the PDF fixture's original page and line identities without changing its text.
    embed=Embedder(ROOT/'models/bge-small-en-v1.5')
    chunks=[]
    for key,text in texts.items():
        path=OUT/'fixtures'/(key+'.txt');path.write_text(text,encoding='utf-8')
        extraction=extract(path) if key!='pdf' else Extraction([Page('Synthetic manual cover',1),Page('',2),Page('Pump P-404 inspection interval is 30 days.',3)],[],hashlib.sha256(text.encode()).hexdigest())
        chunks+=chunk_pages(extraction,embed.tokenizer,key,key+'.txt')
    qa=ROOT/'outputs/full-qa-audit/documents/fixtures'
    for name in ['qa-source.txt','qa-source.xlsx','qa-unicode-தமிழ்.txt']:
        path=qa/name
        if path.exists():
            target=OUT/'fixtures'/name;shutil.copyfile(path,target)
            chunks+=chunk_pages(extract(target),embed.tokenizer,name,name)
    prior=ROOT/'evidence/latency-rag-recovery/20261008-111636/README.md'
    shutil.copyfile(prior,OUT/'fixtures/README.md')
    chunks+=chunk_pages(extract(OUT/'fixtures/README.md'),embed.tokenizer,'readme','README.md')
    queries=[{'id':i,'question':q,'scope':scope,'oracle_documents':scope,'oracle_kind':'source association; full relevance grades require review'} for i,q,scope in cases]
    for i,q,_ in literal(ROOT/'experiments/latency_rag/run.py','QUESTIONS'):
        queries.append({'id':'readme-'+i,'question':q,'scope':['readme'],'oracle_documents':None,'oracle_kind':'UNKNOWN: passage relevance not independently graded'})
    for i,q in enumerate(['What Python version does the document require for installation?','What version is required?','Why is that version required?']):
        queries.append({'id':'followup-'+str(i),'question':q,'scope':['readme'],'oracle_documents':None,'sequence':'followup','oracle_kind':'UNKNOWN until independent conversational review'})
    save('chunks.json',[c.to_dict() for c in chunks]);save('queries.json',queries)
    save('manifest.json',{'files':{str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (OUT/'fixtures').iterdir()},'chunks_sha256':hashlib.sha256((OUT/'chunks.json').read_bytes()).hexdigest(),'queries_sha256':hashlib.sha256((OUT/'queries.json').read_bytes()).hexdigest(),'models':{'e5':'d128750597153bb5987e10b1c3493a34e5a4502a','bgem3':'5617a9f61b028005a4858fdac845db406aefb181','reranker':'953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e'},'policy':{'final_k':6,'reranker_candidates':20,'rrf_k':60,'context':16384,'output_tokens':4096,'temperature':0,'repeats':3,'embedding_device':'cpu','reranker_device':'cpu','training':False},'coverage_gaps':['No existing frozen temporal-version query identified; UNKNOWN','No standalone Unicode query oracle identified; UNKNOWN','Structured document ingested; no new query fabricated'],'baseline':'Unchanged rag.retrieve.retrieve; retained as rollback. Candidates isolated until complete semantic review.'})
    print(OUT,'chunks',len(chunks),'queries',len(queries))

if __name__=='__main__':main()
