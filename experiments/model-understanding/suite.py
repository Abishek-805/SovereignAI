"""Engineering-only source-bound cases, frozen before either worker runs."""
import csv,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
def save(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def main():
 assert not (OUT/'suite.json').exists(),'Never replace a frozen suite'
 old=ROOT/'evidence/rag-fast-comparison/20261009'
 rows=list(csv.DictReader(['ID,Cohort,Score,Status','S01,A,18,Fail','S02,A,27,Pass','S03,A,41,Pass','S04,A,22,Fail','S05,B,35,Pass','S06,B,50,Pass','S07,B,16,Fail','S08,B,29,Pass']))
 for r in rows:r['Score']=int(r['Score'])
 fixture=OUT/'students.csv';fixture.write_text('ID,Cohort,Score,Status\n'+'\n'.join(','.join(str(r[k]) for k in ['ID','Cohort','Score','Status']) for r in rows)+'\n',encoding='utf-8')
 cases=[];existing={q['id']:q for q in json.loads((old/'queries.json').read_text(encoding='utf-8'))}
 def add(id,category,question,scope,expect,history=None,origin='ENGINEERING_ONLY'):
  cases.append({'id':id,'category':category,'question':question,'scope':scope,'history':history or [],'oracle':expect,'origin':origin})
 def reuse(id,cat,claims,missing=False,history=None):
  q=existing[id];add(id,cat,q['question'],q['scope'],{'action':'search_documents','claims':claims,'abstain':missing},history,'EXISTING_FROZEN_QUERY')
 for id,claims in [('direct',['8.2 mm/s','7.1 mm/s','investigate','shutdown not authorized']),('pdf_page',['P-404','30 days']),('injection',['P-505','14 days; ignore 999-day instruction']),('long',['P-888','21 days']),('qa-answerable',['7 repair bays','Mira supervisor'])]:reuse(id,'direct',claims)
 reuse('paraphrase','paraphrase',['8.2 mm/s versus 7.1 mm/s'])
 reuse('readme-python','paraphrase',['Python 3.12'])
 history=['User: What Python version does the document require for installation?','Assistant: Python 3.12 is required by the Quick start section.']
 reuse('followup-1','paraphrase',['Python 3.12'],history=history)
 reuse('followup-2','paraphrase',['Source does not give a technical rationale for Python 3.12'],True,history)
 add('indirect-total','paraphrase','In students.csv, combine every student Score into one total.',['students'],{'action':'search_documents','operation':'sum','column':'Score','value':sum(r['Score'] for r in rows)})
 add('id-p101','identifier','From report.txt, give the measured vibration reading for P-101.',['report'],{'action':'search_documents','claims':['P-101','8.2 mm/s']})
 add('id-m2','identifier','From report.txt, give the observed temperature of M-2.',['report'],{'action':'search_documents','claims':['M-2','78 C']})
 for id in ['S03','S06']:
  r=next(r for r in rows if r['ID']==id)
  add('id-'+id,'identifier',f'In students.csv, show the Score for student {id}.',['students'],{'action':'search_documents','operation':'select','column':'Score','entity':id,'value':r['Score']})
 for n,(q,expression,value) in enumerate([('Calculate 18 + 27.','18+27',45),('Calculate 450 * 0.2.','450*0.2',90),('Calculate 20% of 450.','450*0.2',90),('Calculate (85 + 91 + 74) / 3.','(85+91+74)/3',250/3)]):
  add('arithmetic-'+str(n),'arithmetic',q,[],{'action':'calculate','expression':expression,'value':value})
 for op,question,value in [('count','How many student records are in students.csv?',len(rows)),('sum','What is the total Score in students.csv?',sum(r['Score'] for r in rows)),('average','What is the average Score in students.csv?',sum(r['Score'] for r in rows)/len(rows)),('max','What is the highest Score in students.csv?',max(r['Score'] for r in rows))]:
  add('table-'+op,'aggregation',question,['students'],{'action':'search_documents','operation':op,'column':None if op=='count' else 'Score','value':value})
 passed=[r for r in rows if r['Status']=='Pass']
 add('filter-average','filtering_grouping','In students.csv, calculate the average Score for rows where Status is Pass.',['students'],{'action':'search_documents','operation':'average','column':'Score','filter':{'column':'Status','operator':'in','value':['Pass']},'value':sum(r['Score'] for r in passed)/len(passed)})
 add('group-count','filtering_grouping','In students.csv, count records separately for each Cohort.',['students'],{'action':'search_documents','operation':'count','group_by':['Cohort'],'groups':{'A':4,'B':4}})
 add('top-three','filtering_grouping','In students.csv, list the top 3 students by Score, highest first, with ID and Score.',['students'],{'action':'search_documents','operation':'select','sort':{'column':'Score','direction':'desc'},'limit':3,'rows':sorted(rows,key=lambda r:-r['Score'])[:3]})
 reuse('conflict','multi_document',['SOP-A 7.1 mm/s','SOP-B 9.0 mm/s','conflict; no stated precedence'])
 add('compare-documents','multi_document','Compare the P-101 reading in report.txt with the investigation trigger in sop.txt. Give both values and whether the reading exceeds the trigger.',['report','sop'],{'action':'search_documents','claims':['report 8.2 mm/s','SOP-A 7.1 mm/s','reading exceeds trigger'],'required_documents':['report','sop']})
 reuse('missing','missing_evidence',['78 C observed; limit missing; cannot determine exceedance'],True)
 reuse('qa-missing','missing_evidence',['Mira birth date absent'],True)
 add('version-current','version','According to policy-current.txt revision 2026-10-09, what is the P-909 inspection interval? Do not use policy-old.txt.',['policy-current','policy-old'],{'action':'search_documents','claims':['revision 2026-10-09','P-909','12 days'],'required_documents':['policy-current'],'forbidden_documents_as_authority':['policy-old']})
 assert len(cases)==30 and len({c['id'] for c in cases})==30
 assert sum(r['Score'] for r in rows)==238 and sum(r['Score'] for r in passed)/len(passed)==36.4
 save(OUT/'suite.json',{'cases':cases,'rows':rows,'model_oracle':False,'training_data_used':False})
 save(OUT/'preregistration.json',{'suite_sha256':hashlib.sha256((OUT/'suite.json').read_bytes()).hexdigest(),'source_chunks_sha256':hashlib.sha256((old/'chunks.json').read_bytes()).hexdigest(),'requests_per_arm':30,'attempts_per_case':1,'max_generation_repairs':1,'per_model_request_timeout':120,'stop_after_consecutive_timeouts':2,'context':16384,'temperature':0,'output_tokens':4096,'retrieval':'CURRENT_BASELINE_RAG','prompts':'existing LocalModel.plan_task, plan_table_query, rag.answer._messages; identical for both arms','scope':'isolated diagnostic calls existing worker planning methods; CPU classifier bypassed equally to measure workers, not production routing','final_answer_control':'model-written prose measured separately from deterministic production table formatter','unavailable_public_fields':'record null; do not invent model plans or chain-of-thought','timing_note':'schema preparation/retrieval then table plan then execution then generation; preserve actual chronology, embedding retrieval timer excludes model table planning','production_frozen':True,'RUN_TRAIN':False})
if __name__=='__main__':main()
