"""Compact audit views; no acceptance decision is made by this display helper."""
import json,sys,re
from pathlib import Path
from experiments.dataset_expansion.prepare import rows

def main(out,category,start,end):
    values=[r for r in rows(out/'reference-candidates.jsonl') if r['category']==category]
    for index,row in enumerate(values[start:end],start):
        contract=row['quality']['oracle'];record={'index':index,'id':row['id']}
        if category=='rag':
            gold=contract['expected'];gold=gold if isinstance(gold,list) else [gold];record['parts']=[]
            for g in gold:
                evidence=next(e for e in row['evidence'] if e['label']==g['label']);text=evidence['text'];a=g['answer_start'];b=a+len(g['answer'])
                # Include full sentence and previous sentence for pronoun binding.
                boundaries=[m.end() for m in re.finditer(r'(?<=[.!?])\s+',text)]
                preceding=[p for p in boundaries if p<=a];left=preceding[-2] if len(preceding)>1 else 0
                right=next((p for p in boundaries if p>=b),len(text))
                record['parts'].append({'question':g['question'],'gold':g['answer'],'source_title':evidence['title'],'context':text[left:right]})
        elif category=='computation':record.update(question=json.loads(row['messages'][1]['content'])['question'],steps=contract['steps'],expected=contract['expected'])
        print(json.dumps(record,ensure_ascii=True))

if __name__=='__main__':main(Path(sys.argv[1]).resolve(),sys.argv[2],int(sys.argv[3]),int(sys.argv[4]))
