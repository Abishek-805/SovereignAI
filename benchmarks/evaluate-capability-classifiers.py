"""Frozen development/calibration -> blind heldout CPU classifier evaluation.

Each method runs in a fresh process. No generation model/tool is executed.
Five latency repetitions per heldout request; report medians, not p95.
"""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
os.environ['MKL_NUM_THREADS']='1'
import argparse,csv,gc,hashlib,json,platform,statistics,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
METHODS=('word','character','hybrid','bge')

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def summary(rows):
    accepted=[row for row in rows if row['decision']!='defer_to_planner']
    confusion={}
    for row in rows:
        confusion.setdefault(row['expected'],{});confusion[row['expected']][row['predicted']]=confusion[row['expected']].get(row['predicted'],0)+1
    recalls={};f1=[]
    for label in sorted({row['expected'] for row in rows}):
        tp=sum(row['expected']==label and row['predicted']==label for row in rows)
        fn=sum(row['expected']==label and row['predicted']!=label for row in rows)
        fp=sum(row['expected']!=label and row['predicted']==label for row in rows)
        recalls[label]=tp/(tp+fn) if tp+fn else None
        f1.append(2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0)
    return {'count':len(rows),'top_label_accuracy':sum(row['predicted']==row['expected'] for row in rows)/len(rows),
            'macro_f1':statistics.mean(f1),'per_class_recall':recalls,
            'accepted_count':len(accepted),'accepted_coverage':len(accepted)/len(rows),
            'accepted_correct':sum(row['predicted']==row['expected'] for row in accepted),
            'accepted_accuracy':sum(row['predicted']==row['expected'] for row in accepted)/len(accepted) if accepted else None,
            'unsafe_mutation_acceptances':sum(row['decision']=='edit_code' and row.get('context',{}).get('mode')!='chat' and not row.get('mutation_permitted',False) for row in rows),
            'general_question_tool_acceptances':sum(row['expected']=='answer' and row['decision'] in {'search_documents','create_report','calculate','vision','edit_code','inspect_code','application_tools'} for row in rows),
            'false_retrieval_acceptances':sum(row['decision'] in {'search_documents','create_report'} and row['expected'] not in {'search_documents','create_report'} for row in rows),
            'ambiguous_mutation_acceptances':sum(row['expected']=='clarify' and row['decision']=='edit_code' for row in rows),
            'median_prediction_ms':statistics.median(row['classifier_time_ms'] for row in rows),'confusion':confusion,
            'failures':[row for row in rows if row['predicted']!=row['expected']]}

def worker(method,version='v2',freeze_only=False):
    import numpy as np,psutil,onnxruntime
    from router.capability_classifier import LinearTfidfCandidate,EmbeddingPrototypeCandidate,HierarchicalCandidate,evaluate_prediction
    from rag.embedding import Embedder
    from backend.settings import Settings
    dev_path=ROOT/f'benchmarks/router-development-{version}.json';dev=read(dev_path)
    process=psutil.Process();gc.collect();rss_before=process.memory_info().rss;started=time.perf_counter()
    encoder=Embedder(Settings().model_dir) if method=='bge' else None
    candidate=(HierarchicalCandidate(dev['training'],method,dev['frozen_hyperparameters']['ridge_alpha'],encoder)
               if version=='v3' else EmbeddingPrototypeCandidate(dev['training'],encoder) if encoder else LinearTfidfCandidate(dev['training'],method,dev['frozen_hyperparameters']['ridge_alpha']))
    setup_ms=(time.perf_counter()-started)*1000;rss_after=process.memory_info().rss
    raw_policy={'minimum_score':-100,'minimum_margin':-100}
    calib=[{**task,**evaluate_prediction(candidate,task,raw_policy)} for task in dev['calibration']]
    score_grid=[.65,.7,.75,.8,.85] if method=='bge' else [-.2,0,.2,.4,.6,.8]
    margin_grid=[.04,.08,.12,.2] if method=='bge' else [.05,.1,.2,.3,.5]
    eligible=[]
    for score in score_grid:
        for margin in margin_grid:
            accepted=[row for row in calib if row['score']>=score and row['margin']>=margin and
                      (version!='v3' or row['hierarchy']['score']>=score and row['hierarchy']['margin']>=margin)]
            if accepted and all(row['predicted']==row['expected'] for row in accepted):eligible.append((len(accepted),score,margin))
    if eligible:
        count,score,margin=max(eligible);policy={'minimum_score':score,'minimum_margin':margin,'selection':'maximum calibration coverage with zero accepted calibration mistakes; stricter score/margin tie break','calibration_accepted':count}
    else:policy={'minimum_score':2,'minimum_margin':2,'selection':'no nonempty safe calibration threshold; all abstain','calibration_accepted':0}
    if version=='v3':policy.update(minimum_parent_score=policy['minimum_score'],minimum_parent_margin=policy['minimum_margin'])
    freeze={'method':method,'development_sha256':sha(dev_path),'module_sha256':sha(ROOT/'router/capability_classifier.py'),'hyperparameters':dev['frozen_hyperparameters'],'policy':policy,'frozen_at':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    suffix='-v3' if version=='v3' else ''
    freeze_path=ROOT/f'benchmarks/router-classifier-freeze-{method}{suffix}.json'
    if freeze_only:
        freeze_path.write_text(json.dumps(freeze,indent=2),encoding='utf-8');print(json.dumps(freeze),flush=True);return
    if version=='v3':
        previous=read(freeze_path)
        assert previous['development_sha256']==freeze['development_sha256'] and previous['policy']==policy,'Frozen policy changed'
        freeze=previous
    else:freeze_path.write_text(json.dumps(freeze,indent=2),encoding='utf-8')
    # Heldout read occurs only after immutable settings/policy were written.
    heldout_path=ROOT/f'benchmarks/router-heldout-{version}.json';heldout=read(heldout_path)
    dev_texts={task['text'].strip().lower() for task in dev['training']+dev['calibration']}
    heldout_texts=[task['text'].strip().lower() for task in heldout['tasks']+heldout['safety_probes']]
    overlaps=[{'split':split,'id':task['id'],'text':task['text'],'reason':'Exact normalized development/evaluation overlap excluded before scoring'}
              for split in ('tasks','safety_probes') for task in heldout[split] if task['text'].strip().lower() in dev_texts]
    if version!='v3':assert not overlaps,'Exact train/evaluation text leakage'
    rows=[]
    for split in ('tasks','safety_probes'):
        for task in heldout[split]:
            if version=='v3' and task['text'].strip().lower() in dev_texts:continue
            predictions=[evaluate_prediction(candidate,task,policy) for _ in range(5)]
            row={**task,**predictions[0],'split':split,'classifier_time_ms':statistics.median(item['classifier_time_ms'] for item in predictions),
                 'latency_samples_ms':[item['classifier_time_ms'] for item in predictions]}
            row['failure_category']=('abstention' if row['decision']=='defer_to_planner' else 'capability_classification' if row['predicted']!=row['expected'] else None)
            row['selected_model']=None;row['tools_executed']=False;row['evidence_correctness']=None;row['resource_measurements']=None
            rows.append(row)
    if version=='v3':
        for row in rows:
            row['candidate_decision']=row['decision']
            if row['decision'] not in dev['release_gates']['readonly_labels'] or (
                row['decision']=='edit_code' and row.get('context',{}).get('mode')!='chat'):
                row['decision']='defer_to_planner'
    report={'method':candidate.method,'setup_ms':setup_ms,'sampled_process_rss_before_bytes':rss_before,'sampled_process_rss_after_setup_bytes':rss_after,
            'sampled_rss_increase_bytes':rss_after-rss_before,'embedding_revision':encoder.revision if encoder else None,
            'runtime':{'python':platform.python_version(),'numpy':np.__version__,'onnxruntime':onnxruntime.__version__,'onnx_threads':2 if encoder else None,'blas_threads':1},
            'policy_freeze':freeze,'heldout_sha256':sha(heldout_path),'excluded_exact_overlaps':overlaps,'calibration':calib,'heldout':summary([row for row in rows if row['split']=='tasks']),
            'safety':summary([row for row in rows if row['split']=='safety_probes']),'rows':rows}
    gates=dev['release_gates'];measured=report['heldout'];safety=report['safety']
    failures=[]
    if measured['top_label_accuracy']<gates['minimum_heldout_accuracy']:failures.append('heldout_accuracy')
    if measured['accepted_accuracy'] is None or measured['accepted_accuracy']<gates['minimum_accepted_accuracy']:failures.append('accepted_accuracy')
    if measured['accepted_coverage']<gates['minimum_accepted_coverage']:failures.append('accepted_coverage')
    if safety['accepted_accuracy'] is not None and safety['accepted_accuracy']<gates['minimum_accepted_accuracy']:failures.append('safety_accepted_accuracy')
    for key in ('unsafe_mutation_acceptances','general_question_tool_acceptances','ambiguous_mutation_acceptances','false_retrieval_acceptances'):
        if measured[key] or safety[key]:failures.append(key)
    if gates['independent_human_review_required']:failures.append('independent_human_review_not_completed')
    report['release_gate_failures']=failures;report['production_enabled']=False
    if version=='v3':
        # Chat code is text output; it is never a workspace mutation.
        readonly_errors=[row for row in rows if row['decision']!='defer_to_planner' and row['predicted']!=row['expected']]
        readiness=not failures and not readonly_errors
        manifest={'release_ready':readiness,'production_enabled':False,'root_integration_validation_required':True,
            'feature_mode':method,'development_file':dev_path.name,'development_sha256':sha(dev_path),
            'ridge_alpha':dev['frozen_hyperparameters']['ridge_alpha'],'policy':policy,
            'accepted_labels':dev['release_gates']['readonly_labels'],'heldout_sha256':sha(heldout_path),
            'release_gate_failures':failures,'module_sha256':sha(ROOT/'router/capability_classifier.py')}
        if method!='bge':(ROOT/f'benchmarks/router-classifier-{method}-v3-artifact.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    path=ROOT/f'benchmarks/router-classifier-{method}{suffix}-results.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'method':candidate.method,'setup_ms':setup_ms,'rss_increase_bytes':rss_after-rss_before,'policy':policy,'heldout':{key:value for key,value in measured.items() if key not in {'confusion','failures'}},'safety':{key:value for key,value in safety.items() if key not in {'confusion','failures'}},'release_gate_failures':failures}),flush=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker',choices=METHODS);parser.add_argument('--version',choices=['v2','v3'],default='v2');parser.add_argument('--freeze-only',action='store_true');args=parser.parse_args()
    if args.worker:worker(args.worker,args.version,args.freeze_only);return
    for method in METHODS:subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker',method,'--version',args.version]+(['--freeze-only'] if args.freeze_only else []),cwd=ROOT,check=True)
    if args.freeze_only:return
    suffix='-v3' if args.version=='v3' else ''
    reports=[read(ROOT/f'benchmarks/router-classifier-{method}{suffix}-results.json') for method in METHODS]
    report={'version':'router-cpu-evaluation-'+args.version,'date':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'production_enabled':False,'heldout_run_count':1,
            'latency_repetitions_per_request':5,'p95_reported':False,'machine':{'platform':platform.platform()},'methods':reports,
            'limitations':['Engineer-authored development and independently agent-authored heldout; not independent human-reviewed truth','Classification only; no model quality or workflow success implied','RSS snapshots are not peaks or exclusively attributable steady-state memory','Uncalibrated ridge scores/cosine similarities are not confidence probabilities','No parameter or threshold revision after heldout read']}
    (ROOT/f'benchmarks/router-classifier-{args.version}-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    fields=['method','split','id','category','text','expected','predicted','decision','score','margin','classifier_time_ms','mutation_permitted','mutation_authorized','failure_category']
    with (ROOT/f'benchmarks/router-classifier-{args.version}-results.csv').open('w',newline='',encoding='utf-8') as handle:
        writer=csv.DictWriter(handle,fieldnames=fields,extrasaction='ignore');writer.writeheader()
        for method in reports:
            for row in method['rows']:writer.writerow(row)

if __name__=='__main__':main()
