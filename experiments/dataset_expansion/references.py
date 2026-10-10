"""Public reference conversions; annotations are provenance, never model scores."""
import hashlib, json, re, sys
from decimal import Decimal
from pathlib import Path
from experiments.dataset_expansion.prepare import rows, save, jsonl, digest
from rag.calculator import evaluate_expression

def message(role, content): return {'role':role,'content':content if isinstance(content,str) else json.dumps(content,ensure_ascii=False)}
def sample(identity, category, family, messages, source, contract, **extra):
    return {'id':identity,'category':category,'family':family,'difficulty':'MEDIUM','messages':messages,'source':source,'quality':{'verified':False,'oracle':contract},**extra}
def source(name, row_id, license, **extra):
    return {'kind':'public_human_reference','dataset':name,'row_id':row_id,'license':license,'not_laptop_model_output':True,**extra}
def answer(text, citations):return {'status':'answered','answer':text,'citations':citations}

def prepare(out):
    destination=out/'reference-candidates.jsonl'
    if destination.exists(): return
    candidates=[];articles=json.loads((out/'sources/squad.json').read_text(encoding='utf-8'))['data']
    # Selection is by source digest, not by response difficulty or observed model outcomes.
    articles.sort(key=lambda a:hashlib.sha256(a['title'].encode()).hexdigest())
    eligible=[]
    for article in articles:
        options=[(p,q) for p in article['paragraphs'] for q in p['qas'] if not q['is_impossible'] and q['answers'] and len(p['context'])<5000]
        if options:eligible.append((article,options))
    assert len(eligible)>=309
    def support(article,p,q,label):
        gold=q['answers'][0];text=p['context'];start=gold['answer_start'];target=gold['text']
        assert text[start:start+len(target)]==target
        return {'label':label,'title':article['title'],'text':text,'source_url':'https://en.wikipedia.org/wiki/'+article['title'],'source_sha256':hashlib.sha256(text.encode()).hexdigest()}, {'question':q['question'],'answer':target,'answer_start':start,'human_annotation_id':q['id'],'label':label}
    cursor=0
    for i in range(160):
        a,options=eligible[cursor];cursor+=1;p,q=options[0];e,g=support(a,p,q,'S1')
        messages=[message('system','Answer the question using only the provided evidence. Give the exact requested fact and cite its source. Unsupported information must be marked unavailable.'),message('user',{'question':q['question'],'retrieved_evidence':[e]}),message('assistant',answer(g['answer'],['S1']))]
        candidates.append(sample('squad-fact-'+q['id'],'rag','article:'+a['title'],messages,source('SQuAD 2.0 train',q['id'],'CC-BY-SA-4.0',attribution='Rajpurkar et al., Stanford; linked Wikipedia article',conversion='exact human-annotated fact, no new factual claim'),{'type':'external human semantic annotation plus span/citation integrity','expected':g,'requires_independent_semantic_review':True},evidence=[e],capability='single-source fact'))
    for i in range(40):
        docs=[];contracts=[];titles=[];qs=[];texts=[]
        for label in ('S1','S2'):
            a,options=eligible[cursor];cursor+=1;p,q=options[0];e,g=support(a,p,q,label);docs.append(e);contracts.append(g);titles.append(a['title']);qs.append(q['question']);texts.append({'question':q['question'],'answer':g['answer'],'source':label})
        messages=[message('system','Resolve every requested part from its own provided source. Return separate answers with source labels; do not merge unrelated facts.'),message('user',{'questions':qs,'retrieved_evidence':docs}),message('assistant',{'status':'answered','answers':texts,'citations':['S1','S2']})]
        candidates.append(sample('squad-dual-'+str(i),'rag','article-pair:'+'|'.join(titles),messages,source('SQuAD 2.0 train',[c['human_annotation_id'] for c in contracts],'CC-BY-SA-4.0',attribution='Rajpurkar et al.; linked Wikipedia articles',conversion='two distinct independently human-annotated questions'),{'type':'two external human semantic annotations; complete part/source binding','expected':contracts,'requires_independent_semantic_review':True},evidence=docs,capability='multi-source complete coverage'))
    for i in range(20):
        a,options=eligible[cursor];cursor+=1;p,q=options[0];other=next(((p2,q2) for p2,q2 in options[1:] if q2['question']!=q['question']),None)
        if not other: continue
        p2,q2=other;e,g=support(a,p,q,'S1');e2,g2=support(a,p2,q2,'S2')
        msgs=[message('system','Keep the provided source context across followups. Answer from evidence and cite the source.'),message('user',{'question':q['question'],'retrieved_evidence':[e,e2]}),message('assistant',answer(g['answer'],['S1'])),message('user',q2['question']),message('assistant',answer(g2['answer'],['S2']))]
        candidates.append(sample('squad-followup-'+q['id'],'rag','article:'+a['title'],msgs,source('SQuAD 2.0 train',[q['id'],q2['id']],'CC-BY-SA-4.0',attribution='Rajpurkar et al.; linked Wikipedia article'),{'type':'human annotated multi-turn reference binding','expected':[g,g2],'requires_independent_semantic_review':True},evidence=[e,e2],capability='multi-turn evidence state'))
    # Separate articles are used for extractive briefs. These are deliberately
    # not represented as verified abstractive summaries.
    for i in range(49):
        a,options=eligible[cursor];cursor+=1;p,q=options[0];sentences=re.split(r'(?<=[.!?])\s+',p['context']);chosen=sentences[:2]
        if len(chosen)<2:continue
        target='\n'.join('- '+s for s in chosen)
        msgs=[message('system','Produce the requested extractive brief without adding or rewriting facts.'),message('user',{'request':'Give the first two complete sentences as two bullets, preserving their wording.','document':p['context'],'source':a['title']}),message('assistant',target)]
        candidates.append(sample('squad-extractive-'+str(i),'summarization','article:'+a['title'],msgs,source('SQuAD 2.0 train',q['id'],'CC-BY-SA-4.0',attribution='Rajpurkar et al.; Wikipedia article '+a['title'],conversion='deterministic extractive brief, not model summarization'),{'type':'full sentence identity and order; no unsupported additions','expected_sentences':chosen,'source_sha256':hashlib.sha256(p['context'].encode()).hexdigest()},capability='extractive brief'))
    used_facts=set()
    for r in rows(out/'sources/openbook.jsonl'):
        fact=r['fact1'].strip()
        if fact.lower() in used_facts:continue
        choices=r['question']['choices'];correct=next(c for c in choices if c['label']==r['answerKey']);used_facts.add(fact.lower())
        msgs=[message('system','Answer the question directly. Choose the correct labeled option; no tools or claimed execution.'),message('user',{'question':r['question']['stem'],'choices':choices}),message('assistant',{'choice':correct['label'],'answer':correct['text']})]
        candidates.append(sample('openbook-'+r['id'],'general_qa','openbook-fact:'+fact.lower(),msgs,source('OpenBookQA additional train',r['id'],'Apache-2.0',attribution='Mihaylov, Clark, Khot and Sabharwal, Allen AI, 2018'),{'type':'externally human-annotated multiple-choice quality contract','expected_choice':r['answerKey'],'expected_text':correct['text'],'supporting_fact':fact,'requires_independent_semantic_review':True},capability='science direct answer'))
        if len(used_facts)==77:break
    # Only calculator-annotated problems with all steps checked are candidates.
    computation=0
    for index,r in enumerate(rows(out/'sources/gsm8k.jsonl')):
        steps=re.findall(r'<<([^<>]+)>>',r['answer']);checked=[]
        try:
            for step in steps:
                expression,expected=step.rsplit('=',1);computed=evaluate_expression(expression).result
                assert Decimal(str(computed).replace(',',''))==Decimal(expected.replace(',',''))
                checked.append({'expression':expression,'expected':expected,'actual':str(computed)})
            expected=r['answer'].rsplit('#### ',1)[1].strip().replace(',','')
            assert checked and Decimal(checked[-1]['actual'])==Decimal(expected)
        except (Exception):continue
        msgs=[message('system','Use the supplied verified calculator observations to answer the question. These observations are actual deterministic evaluation, not proof of model reasoning.'),message('user',{'question':r['question'],'verified_calculator_results':checked}),message('assistant','The result is '+expected+'.')]
        candidates.append(sample('gsm8k-'+str(index),'computation','gsm8k:'+str(index),msgs,source('GSM8K train',index,'MIT',attribution='Cobbe et al., OpenAI, 2021',conversion='calculator steps independently evaluated; original worked solution retained in provenance'),{'type':'all annotated arithmetic steps independently evaluated using allowlisted Decimal calculator','expected':expected,'steps':checked,'human_worked_solution':r['answer'],'requires_independent_semantic_review':True},capability='multi-step verified arithmetic'))
        computation+=1
        if computation==44:break
    jsonl(destination,candidates)
    save(out/'reference-candidates-hash.json',{'sha256':digest(destination),'count':len(candidates),'generation':'public-reference conversions; no local-model inference; originals retained','frozen_before_verification':True})
    print('Reference candidates',len(candidates),flush=True)

def verify(out):
    from collections import Counter
    accepted=[];quarantine=[];checks=[]
    for row in rows(out/'reference-candidates.jsonl'):
        contract=row['quality']['oracle'];kind=contract['type'];passed=False
        try:
            assistants=[m for m in row['messages'] if m['role']=='assistant'];expected=contract.get('expected')
            if row['category']=='rag':
                expected=expected if isinstance(expected,list) else [expected]
                values=[]
                for m in assistants:
                    obj=json.loads(m['content']);values.extend(obj.get('answers',[obj]))
                assert len(values)==len(expected)
                for value,g in zip(values,expected):
                    assert value['answer']==g['answer']
                    evidence=next(e for e in row['evidence'] if e['label']==g['label'])
                    assert evidence['text'][g['answer_start']:g['answer_start']+len(g['answer'])]==g['answer']
                    assert value.get('source')==g['label'] or g['label'] in value['citations']
            elif row['category']=='summarization':
                assert assistants[-1]['content']=='\n'.join('- '+s for s in contract['expected_sentences'])
                document=json.loads(row['messages'][1]['content'])['document']
                assert re.split(r'(?<=[.!?])\s+',document)[:2]==contract['expected_sentences']
            elif row['category']=='general_qa':
                answer_obj=json.loads(assistants[-1]['content'])
                assert answer_obj=={'choice':contract['expected_choice'],'answer':contract['expected_text']}
            elif row['category']=='computation':
                for step in contract['steps']:assert Decimal(str(evaluate_expression(step['expression']).result))==Decimal(step['expected'].replace(',',''))
                assert assistants[-1]['content']=='The result is '+expected+'.'
            passed=True
        except Exception as exc:row['rejection']=str(exc)
        record={'id':row['id'],'passed':passed,'oracle_type':kind,'external_human_labels_used':True,'semantic_review_required_for_release':contract.get('requires_independent_semantic_review',False)}
        checks.append(record)
        # Independent public labels are retained as candidate reference data.
        # Their integrity pass must never be relabeled as a fresh semantic audit.
        if passed and not contract.get('requires_independent_semantic_review'):
            row['quality']['verified']=True;row['quality']['oracle']['passed']=True;accepted.append(row)
        else:
            row['quality']['verified']=False;row['rejection']=row.get('rejection','NEEDS_INDEPENDENT_SEMANTIC_REVIEW');quarantine.append(row)
    jsonl(out/'reference-verified.jsonl',accepted);jsonl(out/'reference-quarantine.jsonl',quarantine);save(out/'reference-oracles.json',checks)
    print('Reference integrity',Counter(r['category'] for r in accepted),'; awaiting semantic review',len(quarantine),flush=True)

if __name__=='__main__':
    out=Path(sys.argv[1]).resolve();prepare(out);verify(out)

