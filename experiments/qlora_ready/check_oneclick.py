"""CPU-only structural and resume/failure tests; no generated code execution."""
import ast
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path
from build_oneclick import build


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj


def check():
    out=build()
    p=module('oneclick_pipeline',out/'pipeline.py')
    notebook=json.loads((out/'SovereignAI_OneClick_Readiness.ipynb').read_text())
    code=[''.join(c['source']) for c in notebook['cells'] if c['cell_type']=='code']
    assert len(code)==15
    defined=set()
    for source in code:
        tree=ast.parse(source)
        # Notebook cross-cell names must be created before their first read.
        loads={n.id for n in ast.walk(tree) if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Load)}
        stores={n.id for n in ast.walk(tree) if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Store)}
        stores|={n.name for n in ast.walk(tree) if isinstance(n,ast.ExceptHandler) and n.name}
        imports={a.asname or a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom)) for a in n.names}
        import builtins
        assert loads<=defined|stores|imports|set(dir(builtins)),loads-defined-stores-imports-set(dir(builtins))
        defined|=stores|imports
    stages=[]
    for source in code:
        for n in ast.walk(ast.parse(source)):
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='stage':stages.append(n.args[0].value)
    assert stages==['environment','acquire','base-load','base-smoke','baseline','qlora-smoke','fit']
    assert 'RUN_TRAIN = False' in code[0] and 'assert RUN_TRAIN is False' in code[-1]
    assert not any('pipeline.stage("train")' in source for source in code)
    assert 'torch' not in {a.name for n in ast.walk(ast.parse(code[0])) if isinstance(n,ast.Import) for a in n.names}
    assert set(p.DEPS)=={'environment','integrity','acquire','base-load','base-smoke','baseline','qlora-smoke','fit'}
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary)
        boot=root/'boot';boot.mkdir();(boot/'worker.py').write_text('# fake trusted worker\n')
        hashes={'worker.py':p.digest(boot/'worker.py')}
        pipeline=p.Pipeline(root/'workspace',boot,hashes)
        pipeline.run=root/'workspace/runs/test';pipeline.run.mkdir(parents=True)
        pipeline.binding='test'
        pipeline.data.mkdir()
        p.save(pipeline.data/'package-manifest.json',{'files':{'train.adjusted.jsonl':'fixture-hash'}})
        calls=[]
        def success(args,log):
            calls.append(args[3]);log.write_text('fake structural execution\n')
            p.save(log.parent/'result.json',{'status':'PASS'});return 0
        pipeline.command=success
        pipeline.stage('environment')
        pipeline.stage('integrity')
        assert calls==['environment','integrity']
        pipeline.stage('integrity')
        assert calls==['environment','integrity'], 'Valid receipt was not reused'
        receipt=next((pipeline.run/'stages/integrity').glob('*/receipt.json'))
        (receipt.parent/'result.json').write_text('corrupt')
        pipeline.stage('integrity')
        assert calls==['environment','integrity','integrity'], 'Corrupted artifacts must be rerun'
        assert receipt.parent.exists(), 'Prior evidence deleted'
        pipeline.command=lambda args,log: (log.write_text('CUDA out of memory\n') and 1)
        pipeline.stage('acquire')
        assert pipeline.blocker['gate']=='acquire'
        count=len(calls);pipeline.stage('base-load');assert len(calls)==count
        pipeline.report()
        assert p.read(pipeline.run/'final-status.json')['status']=='TRAINING_BLOCKED'
        assert (pipeline.run/'TRAINING_READINESS_EXECUTION_REPORT.md').exists()
        pipeline.baseline_export()
        exported=pipeline.export()
        import zipfile
        with zipfile.ZipFile(exported) as evidence:
            assert evidence.testzip() is None
            assert {'final-status.json','training-config-final.json','artifact-hashes.json',
                    'TRAINING_READINESS_EXECUTION_REPORT.md','baseline-summary.json'}<=set(evidence.namelist())
            assert any(n.endswith('execution.log') for n in evidence.namelist())
        try:pipeline.stage('train')
        except AssertionError:pass
        else:raise AssertionError('Full training exposed')
    # Test real dataset identity/count checks without touching model packages.
    import sys
    sys.path.insert(0,str(out))
    worker=module('oneclick_worker_test',out/'worker.py')
    package=Path(__file__).resolve().parents[2]/'evidence/pretraining-readiness/20261008-173531/colab-package'
    wanted=worker.expected(package)
    predictions=[{'id':row['id'],'split':s,'category':row['category'],'model':worker.r.MODEL,
                  'revision':worker.r.REVISION,'adapter':None,'dataset_sha256':worker.r.digest(package/(s+'.adjusted.jsonl')),
                  'code_executed':False,'independent_status':'NOT_TESTED','raw_output':'synthetic validation fixture','generated_tokens':1}
                 for s,row in wanted]
    assert not worker.validate_predictions(package,predictions,complete=True)
    assert len(worker.validate_predictions(package,predictions[:-1]))==1
    for malformed in (predictions+[predictions[0]],predictions[:-1]):
        try:worker.validate_predictions(package,malformed,complete=True)
        except AssertionError:pass
        else:raise AssertionError('Duplicate/incomplete baseline accepted')
    # Exercise the actual checkpoint/resume loop with trusted CPU fixtures, no model inference.
    original={name:getattr(worker.r,name) for name in ('acquire','load','generate','digest')}
    old_expected=worker.expected
    class FakeModel:
        def eval(self):pass
    small=[(s,{**row,'messages':[{'role':'user','content':row['id']},{'role':'assistant','content':'fixture'}]}) for s,row in wanted[:3]]
    worker.expected=lambda data:small
    worker.r.acquire=lambda data,out:Path('fixture-cache')
    worker.r.load=lambda directory:(FakeModel(),object(),{'seconds':0,'fixture':True})
    worker.r.digest=lambda path:'fixture-dataset-hash'
    generated=[]
    def fake_generate(model,tokenizer,messages,tools):
        if len(generated)==1:raise RuntimeError('fixture interruption')
        generated.append(messages[0]['content'])
        return {'raw_output':'fixture','generated_tokens':1}
    worker.r.generate=fake_generate
    with tempfile.TemporaryDirectory() as temporary:
        attempt=Path(temporary)
        try:worker.baseline(Path('fixture'),attempt)
        except RuntimeError:pass
        else:raise AssertionError('Fixture interruption not raised')
        records=list((attempt/'records').glob('*.json'));assert len(records)==1
        first_hash=hashlib.sha256(records[0].read_bytes()).hexdigest()
        # Resume processes only the two uncaptured records, then deliberately fails
        # the authoritative 131-count check (the three-row fixture is not a real baseline).
        worker.r.generate=lambda model,tokenizer,messages,tools:(generated.append(messages[0]['content']) or {'raw_output':'fixture','generated_tokens':1})
        # Cleanup is the only torch call in this CPU fixture.
        import types
        prior_torch=sys.modules.get('torch')
        sys.modules['torch']=types.SimpleNamespace(cuda=types.SimpleNamespace(empty_cache=lambda:None))
        try:
            try:worker.baseline(Path('fixture'),attempt)
            except AssertionError:pass
            else:raise AssertionError('Non-131 fixture accepted as completed baseline')
        finally:
            if prior_torch is None:sys.modules.pop('torch',None)
            else:sys.modules['torch']=prior_torch
        assert len(generated)==3 and len(set(generated))==3
        assert hashlib.sha256(records[0].read_bytes()).hexdigest()==first_hash
    worker.expected=old_expected
    for name,value in original.items():setattr(worker.r,name,value)
    report={'status':'PASS','notebook_code_cells':15,'syntax_and_cross_cell_name_checks':'PASS',
            'ordered_stages':'PASS','receipt_reuse_and_corruption_checks':'PASS','failure_stops_dependents':'PASS',
            'training_guard':'PASS','exact_baseline_identity_counts_duplicates':'PASS',
            'per_record_interruption_resume_without_overwrite':'PASS',
            'failure_evidence_zip_contents_and_crc':'PASS',
            'GPU_probes_executed':False,'production_changed':False,'dataset_changed':False}
    (out/'local-validation-report.json').write_text(json.dumps(report,indent=2)+'\n')
    (out/'LOCAL_VALIDATION_REPORT.md').write_text('# Local validation\n\nPASS\n\n```json\n'+json.dumps(report,indent=2)+'\n```\n\nNo Colab execution or GPU/QLoRA/fit success is claimed. No generated project code was executed.\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':check()
