"""Explicit human-agent review decisions; original quarantines stay immutable."""
import copy,hashlib,json,sys
from pathlib import Path
from experiments.dataset_expansion.prepare import ROOT,rows,save,jsonl,digest

RAG_REJECT={2:'A yes/no question received an incomplete sentence fragment rather than the requested answer.',15:'The source dates computer use, not the beginning of computer manufacturing; temporal relation is not entailed.',78:'Answer omits Taiwan and overseas communities from the requested locations.',91:'Environmental lighting is not an atmosphere type; question and answer have incompatible semantic types.',105:'The definition omits the essential federal/regional-government combination.',127:'Electric current is not a type of energy; question/answer type mismatch.',136:'A shared transborder conurbation does not independently establish a municipal boundary.',139:'A see-also link does not establish that the referenced movement is a synonym.',166:'An Italian word does not independently establish the country of instrument origin.',168:'First target contains an unmatched quotation mark.',170:'Date of an antecedent event does not establish the date of creation.',172:'The requested full university name is truncated before Lac.',179:'Europe is a continent, not a country; the evidence lists eight countries.',181:'A region having a mainly Armenian population does not establish where most Armenians live.',188:'The source limits the brain claim to vertebrates and most invertebrates; the question falsely universalizes all creatures.',195:'The current-superlative question is answered from an undated historical monarch snapshot without adequate temporal qualification.',205:'Requested states are replaced by a mixed list of oceans, straits and states.',216:'Answer omits scripture authority and grace/faith from the requested theological emphases.',217:'A field list does not establish that philology is the proper name for all textual scholarship.'}

def main(out):
    source_rows=rows(out/'reference-candidates.jsonl');rag=[r for r in source_rows if r['category']=='rag'];computations=[r for r in source_rows if r['category']=='computation']
    assert len(rag)==220 and len(computations)==44
    positives=[];negatives=[];decisions=[]
    for i,original in enumerate(rag):
        candidate=copy.deepcopy(original);passed=i not in RAG_REJECT
        candidate['id']+='-semantic-reviewed';candidate['source']['original_candidate_id']=original['id']
        candidate['quality']['verified']=passed;candidate['quality']['oracle'].update(passed=passed,independent_semantic_review={'reviewer':'Codex independent of original crowdworker answer','question_relation_and_requested_scope_reviewed':True,'support_context_reviewed':True,'all_parts_and_followup_bindings_reviewed':True,'source_relative_not_current_world_truth':True,'decision':'ACCEPT' if passed else 'REJECT','reason':RAG_REJECT.get(i,'The requested fact/relation, quantity or complete component answers are supported by the source context; no additional factual claim was introduced.')})
        if not passed:candidate['rejection']=RAG_REJECT[i]
        (positives if passed else negatives).append(candidate)
        decisions.append({'index':i,'original_id':original['id'],'candidate_sha256':hashlib.sha256(json.dumps(original,sort_keys=True).encode()).hexdigest(),'accepted':passed,'reason':candidate['quality']['oracle']['independent_semantic_review']['reason']})
    for original in computations:
        candidate=copy.deepcopy(original);passed=original['id']!='gsm8k-33'
        candidate['id']+='-semantic-reviewed';candidate['source']['original_candidate_id']=original['id']
        candidate['quality']['verified']=passed;candidate['quality']['oracle'].update(passed=passed,independent_semantic_review={'reviewer':'Codex independent of public worked answer','question_to_step_relations_checked':True,'all_reported_arithmetic_independently_checked':True,'result_unit_scope_checked':True,'reason':'Mixed cups and teaspoons are combined without a physically consistent quantity.' if not passed else 'The supplied arithmetic and final quantity match the stated educational word problem; calculator output is not a model-reasoning claim.'})
        if not passed:candidate['rejection']='DIMENSIONAL_SCOPE_AMBIGUOUS'
        (positives if passed else negatives).append(candidate)
    jsonl(out/'semantic-verified.jsonl',positives);jsonl(out/'semantic-negatives.jsonl',negatives)
    save(out/'independent-semantic-review.json',{'reference_candidates_sha256':digest(out/'reference-candidates.jsonl'),'rag_reviewed':220,'rag_accepted':220-len(RAG_REJECT),'rag_rejected':RAG_REJECT,'computation_reviewed':44,'computation_accepted':43,'original_candidates_and_quarantine_unchanged':True,'decisions':decisions,'limitations':['RAG is source-relative to public historical text, not current world fact evaluation.','Source windows were reviewed; full paragraphs were read for ambiguous abbreviation/relation cases.','Extractive references do not establish general abstractive reasoning.']})
    print('Semantic accepted',len(positives),'rejected',len(negatives),flush=True)

if __name__=='__main__':main(Path(sys.argv[1]).resolve())
