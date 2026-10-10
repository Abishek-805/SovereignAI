"""One source-bound meeting decision reference, not a cosmetic summary-prompt variant."""
import json,sys
from pathlib import Path
from experiments.dataset_expansion.prepare import save,jsonl,digest
from experiments.dataset_expansion.references import sample,message

def acquire(out):
    notes=[
        {'label':'S1','text':'Chair proposed a Sunday cutover and initially suggested Operations should monitor it. Neither proposal was approved at this point.'},
        {'label':'S2','text':'Ada objected that the audit occupies Sunday. Chair accepted the objection and approved cutover on 18 June at 09:00 UTC instead. Chair assigned monitoring to Lin, replacing the initial suggestion.'},
        {'label':'S3','text':'Lin accepted monitoring ownership. Dev agreed to complete backups by 17 June at 17:00 UTC. Renewal pricing has not been supplied; the renewal-budget decision was deferred, not approved.'}
    ]
    request='Turn these meeting notes into a decision handover: state the adopted decision, the rejected proposal and why, named owners with their commitments, and the decision still deferred. Do not present proposals as agreements.'
    target={'decision':'Cutover is approved for 18 June at 09:00 UTC.','rejected':'Sunday cutover was rejected because of the audit. The initial Operations monitoring suggestion was superseded.','commitments':[{'owner':'Lin','action':'Monitor the cutover.'},{'owner':'Dev','action':'Complete backups by 17 June at 17:00 UTC.'}],'deferred':'Renewal-budget approval is deferred because renewal pricing is unavailable.'}
    directory=out/'summary-raw/meeting-decision-handover';directory.mkdir(parents=True,exist_ok=True)
    source={'request':request,'notes':notes}
    source_path=directory/'source.json'
    if source_path.exists():assert json.loads(source_path.read_text(encoding='utf-8'))==source
    else:save(source_path,source)
    save(directory/'candidate.json',{'answer':target,'author':'offline operator reference','provider_model_calls':0})
    review={'passed':True,'reviewer':'Codex in a separate source/target semantic review phase; no laptop model or external judging service','scope':'Answer-bound factual claims and complete requested coverage, not JSON shape or keywords alone.','claims':[
        {'target':'adopted cutover/time','source':'S2','decision':'ACCEPT','reason':'The chair explicitly approves the replacement date/time; the proposal is not treated as an agreement.'},
        {'target':'Sunday rejection and cause','source':'S2','decision':'ACCEPT','reason':'The stated audit objection is accepted by the chair.'},
        {'target':'superseded Operations suggestion','source':'S1,S2','decision':'ACCEPT','reason':'S1 is explicitly unapproved and S2 replaces the suggested owner with Lin.'},
        {'target':'Lin monitoring commitment','source':'S2,S3','decision':'ACCEPT','reason':'Assignment and explicit acceptance both appear in the source.'},
        {'target':'Dev backup deadline','source':'S3','decision':'ACCEPT','reason':'Owner, action and deadline are explicit; the cutover date is not substituted for the backup deadline.'},
        {'target':'renewal approval deferred/pricing absent','source':'S3','decision':'ACCEPT','reason':'The source explicitly distinguishes deferral from approval and says pricing is unavailable.'}
    ],'negative_controls_reviewed':[{'claim':'Sunday cutover approved','decision':'REJECT','reason':'Contradicts the accepted replacement date.'},{'claim':'Operations is the final monitoring owner','decision':'REJECT','reason':'The suggestion was replaced by Lin.'},{'claim':'Renewal budget approved','decision':'REJECT','reason':'The source explicitly defers approval.'}],'no_unsupported_cost_or_causation_added':True,'all_requested_sections_present':True,'source_sha256':digest(source_path)}
    save(directory/'semantic-oracle.json',review)
    row=sample('final-summary-meeting-handover','summarization','operator-meeting-decision-handover',[message('system','Summarize decisions from source notes. Preserve proposal/agreement distinctions, updated ownership, dates and explicit uncertainty.'),message('user',{'request':request,'sources':notes}),message('assistant',target)],{'kind':'OPERATOR_AUTHORED','license':'operator-authored fixture','not_laptop_model_output':True,'provider_model_calls':0,'raw_source':str(source_path)}, {'type':'separate source-bound claim/relation/coverage semantic review and contradictory-answer negative controls','passed':True,'evidence':str(directory/'semantic-oracle.json')},capability='multi-source meeting decision handover',difficulty='HARD')
    row['quality']['verified']=True
    jsonl(out/'new-summary-positive.jsonl',[row])
    print('One meeting decision reference acquired; semantic review PASS, no model calls.')

if __name__=='__main__':acquire(Path(sys.argv[1]).resolve())
