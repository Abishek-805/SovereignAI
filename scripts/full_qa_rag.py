import json,re
from scripts.full_qa_inventory import http,save,OUT
from scripts.verify_product_completion import job as oldjob
entries=json.loads((OUT/'document-audit.json').read_text(encoding='utf-8'))['cases']
ids={c['name']:c.get('document_id') for c in entries if c.get('document_id')}
results=[]
def ask(case,question,docs,expected=None,history=None):
 r=http('/ask','POST',{'question':question,'document_ids':docs,'history':history or []})
 b=r.get('body',{});answer=b.get('answer','') if isinstance(b,dict) else ''
 sources=b.get('sources',[]) if isinstance(b,dict) else []
 oracle='Source association and required values' if expected else 'Response recorded for independent semantic review'
 passed=r['status']==200 and bool(answer) and (all(re.search(pattern,answer,re.I) for pattern in expected) if expected else True)
 if sources and any(s.get('document_id') not in docs for s in sources):passed=False
 if expected and not sources:passed=False
 r.update(case=case,answer=answer,verdict='PASS' if passed else 'FAIL' if r['status'] else 'BLOCKED',oracle=oracle)
 save('rag/'+case+'.json',r);results.append(r);print(case,r['verdict'],round(r['latency'],1),flush=True);return answer
if ids.get('qa-source.txt'):
 d=ids['qa-source.txt']
 a=ask('answerable','How many repair bays does the audit laboratory have and who is its supervisor? Cite the source.',[d],['7|seven','Mira',r'\[S\d+\]'])
 ask('not-in-source','What is the supervisor Mira\'s birth date? Use only the selected source.',[d])
 ask('negative-claim','Does the laboratory permit external network access? Use only the source.',[d],['prohibit|not permit|not allow|no'])
 ask('followup','Who supervises it?',[d],['Mira'],['User: How many repair bays does the audit laboratory have?', 'Assistant: '+a])
 ask('bare-followup','Mira',[d],None,['User: Who supervises the audit laboratory?','Assistant: Mira supervises it.'])
 ask('source-name','According to qa-source.txt, how many repair bays are there?',[d],['7|seven'])
 ask('multi-source','Summarize the laboratory facts in these selected documents and cite sources.',[d,ids['qa-source.docx']],['Mira','7|seven'])
if ids.get('qa-source.xlsx'):
 d=ids['qa-source.xlsx']
 for case,q,pattern in [('cohort-count','How many ALR students are listed?',['3|three']),('label-count','How many ALR students have explicit Result PASS?',['1|one']),('numeric-rule','Count ALR students with Score at least 25. Include missing scores in the population denominator.',['1|one']),('sum','What is the sum of the numeric Score values for ALR students? Ignore blank scores.',['49']),('average','What is the average of the numeric Score values for ALR students? Ignore blank scores.',['24.5']),('minimum','What is the minimum numeric Score for ALR students?',['24']),('maximum','What is the maximum numeric Score for ALR students?',['25'])]:ask('spreadsheet-'+case,q,[d],pattern)
save('rag-audit.json',results)
