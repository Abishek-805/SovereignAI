import json,time,re
from pathlib import Path
from scripts.full_qa_inventory import http
OUT=Path('outputs/release-repair');OUT.mkdir(exist_ok=True)
def save(name,r):
 p=OUT/name
 p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():p.rename(p.with_name(p.stem+'-'+str(time.time_ns())+p.suffix))
 p.write_text(json.dumps(r,indent=2,ensure_ascii=False),encoding='utf-8')
cases=json.loads(Path('outputs/full-qa-audit/document-audit.json').read_text(encoding='utf-8'))['cases'];ids={r['name']:r.get('document_id') for r in cases};counter=json.loads(Path('outputs/full-qa-audit/documents/counterexample-import.json').read_text());cid=counter.get('document_id') or counter.get('document',{}).get('document_id')
queries=[('numeric-rule',ids['qa-source.xlsx'],'Count ALR students with Score at least 25. Include missing scores in the population denominator.',1,3),('counterexample',cid,'Count ALR students with Score at least 25. Include missing scores in the population denominator.',2,4),('conjunction',cid,'Count ALR students with Result PASS and Score at least 25. Include missing scores in the population denominator.',0,4),('workbook-analysis',ids['qa-source.xlsx'],'Analyze this workbook. Summarize the number of records, cohort counts, and numeric Score totals. Do not invent a pass threshold.',None,None)]
for id,did,q,count,total in queries:
 r=http('/ask','POST',{'question':q,'document_ids':[did],'history':[]});r['oracle']={'count':count,'total':total} if count is not None else {'records':4,'ALR':3,'ADR':1,'score_sum':79};save('rag/'+id+'.json',r);print(id,r['status'],str(r['body'].get('answer'))[:600],flush=True)
