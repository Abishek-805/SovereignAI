"""Standard-library Colab coordinator. No model imports or training entry point."""
import datetime
import hashlib
import importlib.metadata as md
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

PACKAGE_SHA='11179a62a2fb762dd81920e975ece57d20741316abd7382b1d1d995ea2b209d3'
MODEL='Qwen/Qwen3.5-4B-Base'
REVISION='1001bb4d826a52d1f399e183466143f4da7b741b'
PINS={'torch':'2.11.0+cu130','transformers':'5.19.0','peft':'0.21.1','bitsandbytes':'0.50.2','accelerate':'1.15.0','datasets':'4.8.5'}
DEPS={'environment':[], 'integrity':['environment'], 'acquire':['integrity'],
      'base-load':['acquire'], 'base-smoke':['base-load'], 'baseline':['base-smoke'],
      'qlora-smoke':['baseline'], 'fit':['qlora-smoke']}


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2,ensure_ascii=False,default=str)+'\n',encoding='utf-8')
    os.replace(temporary,path)


class Pipeline:
    def __init__(self, root, boot, hashes):
        self.root=Path(root);self.boot=Path(boot);self.hashes=hashes
        self.data=self.root/'package';self.run=None;self.blocker=None;self.stages={}
        self.root.mkdir(parents=True,exist_ok=True)
        self.signature={'package':PACKAGE_SHA,'model':MODEL,'revision':REVISION,'code':hashes,
                        'python':sys.version,'platform':platform.platform()}
        self.pending=self.root/('setup-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))
        self.pending.mkdir()

    def verify_code(self):
        for name,value in self.hashes.items():assert digest(self.boot/name)==value, 'Notebook supporting code mismatch: '+name

    def command(self,args,log):
        log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('w',encoding='utf-8') as f:
            process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,
                                     env={**os.environ,'PYTHONHASHSEED':'42','CUBLAS_WORKSPACE_CONFIG':':4096:8'})
            try:
                for line in process.stdout:
                    f.write(line);f.flush();print(line,end='',flush=True)
                return process.wait()
            except BaseException:
                process.terminate()
                try:process.wait(timeout=15)
                except subprocess.TimeoutExpired:process.kill();process.wait()
                raise

    def install(self):
        try:
            self.verify_code()
            assert md.version('torch')==PINS['torch'], 'Pinned CUDA PyTorch unavailable; no substitution'
            req=self.pending/'requirements.txt';constraints=self.pending/'constraints.txt'
            req.write_text('\n'.join(k+'=='+v for k,v in PINS.items() if k!='torch')+'\n')
            constraints.write_text('torch=='+PINS['torch']+'\n')
            rc=self.command([sys.executable,'-m','pip','install','-r',str(req),'-c',str(constraints),
                             '--report',str(self.pending/'pip-report.json')],self.pending/'pip-install.log')
            assert rc==0, 'Pinned pip installation failed'
            versions={k:md.version(k) for k in PINS}
            assert versions==PINS, ('Dependency version mismatch',versions)
            rc=self.command([sys.executable,'-m','pip','check'],self.pending/'pip-check.log')
            assert rc==0, 'Dependency conflicts; do not repair by changing pins'
            gpu=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,driver_version','--format=csv,noheader'],capture_output=True,text=True,check=True).stdout.strip()
            self.signature.update(versions=versions,gpu_identity=gpu)
            self.binding=hashlib.sha256(json.dumps(self.signature,sort_keys=True).encode()).hexdigest()
            latest=self.root/'runs/latest/manifest.json'
            if latest.exists() and read(latest)['binding']==self.binding:
                self.run=self.root/read(latest)['run']
                assert self.run.resolve().is_relative_to((self.root/'runs').resolve()) and self.run.is_dir()
            else:
                self.run=self.root/'runs'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
                self.run.mkdir(parents=True)
            save(latest,{'binding':self.binding,'run':str(self.run.relative_to(self.root))})
            target=self.run/'setup'/self.pending.name
            target.parent.mkdir(exist_ok=True);shutil.move(str(self.pending),str(target))
            save(target/'installed-versions.json',{'versions':versions,'python':sys.version,'pip_check':'PASS',
                 'restart_required':False,'reason':'All model/library execution uses fresh child interpreters; notebook imports standard library only',
                 'distribution_record_hashes':{k:digest(md.distribution(k).locate_file(next(f for f in md.distribution(k).files if str(f).endswith('.dist-info/RECORD')))) for k in PINS}})
            save(self.run/'execution-metadata.json',{'binding':self.binding,'signature':self.signature,
                 'storage':'Colab session disk; survives browser disconnect/session restart, not runtime deletion',
                 'training_enabled':False,'one_heavy_model_at_a_time':True})
        except Exception as e:self.fail('dependencies',e)

    def fail(self,gate,error):
        self.blocker={'gate':gate,'error':repr(error),'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        location=self.run or self.pending
        save(location/('failure-'+datetime.datetime.now(datetime.timezone.utc).strftime('%H%M%S-%f')+'.json'),self.blocker)
        print('STOP DEPENDENT PIPELINE:',self.blocker,flush=True)

    def package(self):
        if self.blocker:return
        try:
            archive=Path('/content/sovereignai-pretraining-readiness-colab.zip')
            if not archive.exists():
                from google.colab import files
                uploaded=files.upload()
                assert set(uploaded)=={archive.name}, 'Upload exactly the expected ZIP'
                assert hashlib.sha256(uploaded[archive.name]).hexdigest()==PACKAGE_SHA, 'ZIP hash mismatch'
                archive.write_bytes(uploaded[archive.name])
            assert digest(archive)==PACKAGE_SHA, 'ZIP hash mismatch'
            with zipfile.ZipFile(archive) as z:
                assert z.testzip() is None and sum(i.file_size for i in z.infolist())<200_000_000
                for i in z.infolist():
                    p=Path(i.filename)
                    assert not p.is_absolute() and '..' not in p.parts and '\\' not in i.filename
                    assert (i.external_attr>>16)&0o170000!=0o120000
                if not self.data.exists():z.extractall(self.data)
                manifest=read(self.data/'package-manifest.json')
                assert manifest==json.loads(z.read('package-manifest.json')), 'Existing package manifest mismatch'
            for name,value in manifest['files'].items():
                path=(self.data/name).resolve()
                assert path.is_relative_to(self.data.resolve()) and digest(path)==value,name
            assert digest(self.data/'readiness.py')==self.hashes['readiness.py'], 'Pinned runtime code differs'
            save(self.run/'package-verification.json',{'status':'PASS','zip_sha256':digest(archive),
                 'manifest_sha256':digest(self.data/'package-manifest.json'), 'files':manifest['files']})
            self.stage('integrity')
        except Exception as e:self.fail('package',e)

    def valid_receipt(self,path):
        assert path.with_suffix('.sha256').read_text().strip()==digest(path), 'Receipt hash mismatch'
        receipt=read(path)
        assert receipt['binding']==self.binding and receipt['status']=='PASS'
        for name,value in receipt['artifacts'].items():
            f=(path.parent/name).resolve()
            assert f.is_relative_to(path.parent.resolve()) and digest(f)==value
        return receipt

    def stage(self,name):
        assert name in DEPS, 'Unsupported stage: full training unavailable'
        if self.blocker:print(name+': NOT_RUN (prior gate failed)');return
        try:
            assert all(self.stages.get(d,{}).get('status')=='PASS' for d in DEPS[name]), 'Missing prerequisite'
            self.verify_code()
            directory=self.run/'stages'/name;directory.mkdir(parents=True,exist_ok=True)
            # Environment must always be measured on the current runtime.
            candidates=sorted(directory.glob('*/receipt.json'),reverse=True) if name!='environment' else []
            for previous in candidates:
                try:receipt=self.valid_receipt(previous)
                except (AssertionError,OSError,ValueError,KeyError):continue
                if name=='acquire':
                    try:
                        identity=read(previous.parent/'base-model-identity.json')
                        cache=Path(identity['cache_path'])
                        assert digest(cache/'config.json')==identity['config_sha256']
                        for f,h in identity['safetensors_sha256'].items():assert digest(cache/f)==h
                    except (AssertionError,OSError,KeyError,ValueError):continue
                self.stages[name]={'status':'PASS','reused':True,'directory':str(previous.parent.relative_to(self.run))}
                print(name+': verified receipt reused');return
            attempt=directory/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
            attempt.mkdir()
            if name=='baseline':
                unfinished=sorted(directory.glob('*/records'),reverse=True)
                if unfinished:
                    source=unfinished[0]
                    shutil.copytree(source,attempt/'records')
            started=time.perf_counter()
            rc=self.command([sys.executable,'-u',str(self.boot/'worker.py'),name,'--data',str(self.data),
                             '--output',str(attempt)],attempt/'execution.log')
            assert rc==0, f'{name} failed with exit {rc}; see {attempt}/execution.log'
            artifacts={str(f.relative_to(attempt)):digest(f) for f in attempt.rglob('*') if f.is_file() and not f.name.endswith('.tmp')}
            save(attempt/'receipt.json',{'status':'PASS','binding':self.binding,'stage':name,
                 'seconds':time.perf_counter()-started,'artifacts':artifacts,'independent_quality_verified':False})
            attempt.joinpath('receipt.sha256').write_text(digest(attempt/'receipt.json')+'\n')
            self.stages[name]={'status':'PASS','reused':False,'directory':str(attempt.relative_to(self.run))}
        except Exception as e:
            self.stages[name]={'status':'FAIL','directory':str(attempt.relative_to(self.run)) if 'attempt' in locals() else None}
            self.fail(name,e)
        finally:
            if self.run:save(self.run/'pipeline-state.json',{'stages':self.stages,'blocker':self.blocker,'training':'DISABLED'})

    def baseline_export(self):
        if not self.run:return
        baseline=self.run/'stages/baseline'
        attempts=sorted(baseline.glob('*/records'),reverse=True) if baseline.exists() else []
        capture={'status':'NOT_RUN','captured':0,'counts':{'validation':0,'internal-test':0}}
        if attempts and self.data.exists():
            import collections
            expected={(s,row['id']) for s in ('validation','internal-test')
                      for row in [json.loads(line) for line in (self.data/(s+'.adjusted.jsonl')).read_text().splitlines() if line.strip()]}
            values=[]
            for f in attempts[0].glob('*.json'):
                envelope=read(f);prediction=envelope['prediction']
                assert hashlib.sha256(json.dumps(prediction,sort_keys=True,ensure_ascii=False).encode()).hexdigest()==envelope['sha256']
                assert prediction['model']==MODEL and prediction['revision']==REVISION
                assert prediction['dataset_sha256']==digest(self.data/(prediction['split']+'.adjusted.jsonl'))
                values.append(prediction)
            keys=[(v['split'],v['id']) for v in values]
            assert len(keys)==len(set(keys)) and set(keys)<=expected
            capture={'status':'PASS' if set(keys)==expected else 'PARTIAL','captured':len(keys),
                     'counts':dict(collections.Counter(v['split'] for v in values)),
                     'categories':{s:dict(collections.Counter(v['category'] for v in values if v['split']==s)) for s in ('validation','internal-test')},
                     'missing':sorted(expected-set(keys)),'duplicates':0,'independent_status':'NOT_TESTED'}
        save(self.run/'baseline-counts.json',capture)
        summary={'capture':self.stages.get('baseline',{'status':'NOT_RUN'}),
                 'independent_validation':'NOT_TESTED','quality_scores':None,
                 'required':'Source-bound semantic review; existing Docker coding oracles; full stateful agentic rollouts'}
        save(self.run/'baseline-summary.json',summary)
        shutil.make_archive(str(self.run/'baseline-evidence'),'zip',self.run/'stages/baseline') if (self.run/'stages/baseline').exists() else None

    def configuration(self):
        if not self.run:return
        measured=self.stages.get('qlora-smoke',{}).get('status')=='PASS'
        fit=self.stages.get('fit',{}).get('status')=='PASS'
        value=lambda v,s:{'value':v,'status':s}
        config={k:value(v,s) for k,v,s in [
            ('model_revision',REVISION,'VERIFIED' if self.stages.get('acquire',{}).get('status')=='PASS' else 'UNKNOWN'),
            ('tokenizer_revision',REVISION,'VERIFIED' if self.stages.get('acquire',{}).get('status')=='PASS' else 'UNKNOWN'),
            ('dataset_package_sha256',PACKAGE_SHA,'VERIFIED' if self.stages.get('integrity',{}).get('status')=='PASS' else 'UNKNOWN'),
            ('split_counts',{'train':579,'validation':65,'internal-test':66},'VERIFIED' if self.stages.get('integrity',{}).get('status')=='PASS' else 'UNKNOWN'),
            ('sequence_length',4096,'VERIFIED' if fit else 'PROPOSED'),
            ('quantization',{'bits':4,'type':'nf4','double_quant':True},'VERIFIED' if measured else 'PROPOSED'),
            ('lora',{'rank':16,'alpha':32,'dropout':.05,'target':'all-linear','exclude':'visual'},'VERIFIED' if measured else 'PROPOSED'),
            ('optimizer','torch.optim.AdamW','VERIFIED' if measured else 'PROPOSED'),
            ('learning_rate',1e-4,'VERIFIED' if measured else 'PROPOSED'),
            ('microbatch',1,'VERIFIED' if fit else 'PROPOSED'),
            ('gradient_accumulation',16,'PROPOSED'),('epochs',2,'PROPOSED'),('scheduler','linear','PROPOSED'),
            ('warmup_ratio',.03,'PROPOSED'),('seed',42,'VERIFIED' if measured else 'PROPOSED'),
            ('gradient_checkpointing',True,'VERIFIED' if measured else 'PROPOSED'),
            ('evaluation_strategy','epoch + independent source-bound oracles','PROPOSED'),
            ('checkpoint_strategy','epoch; validation oracle selection','PROPOSED'),
            ('assistant_only_loss',True,'VERIFIED' if measured else 'PROPOSED')]}
        precision=None
        if measured:precision=read(self.run/self.stages['qlora-smoke']['directory']/'qlora-smoke-result.json')['precision']
        config['precision']=value(precision,'VERIFIED' if measured else 'UNKNOWN')
        config['RUN_TRAIN']=value(False,'VERIFIED')
        if self.stages.get('integrity',{}).get('status')=='PASS':
            manifest=read(self.data/'package-manifest.json')
            config['adjusted_dataset_hashes']=value({k:v for k,v in manifest['files'].items() if k.endswith('.adjusted.jsonl')},'VERIFIED')
        config['verification_scope']='Runtime feasibility only; hyperparameter quality/long-run stability not established'
        save(self.run/'training-config-final.json',config)

    def report(self):
        location=self.run or self.pending
        self.configuration()
        status='TRAINING_BLOCKED' if self.blocker else 'BASELINE_BLOCKED'
        result={'status':status,'stages':self.stages,'blocker':self.blocker,'training':'DISABLED',
                'independent_baseline':'NOT_TESTED','T01_T15_inspected':False,'dataset_modified':False}
        save(location/'final-status.json',result)
        details=[]
        for stage,v in self.stages.items():
            if not v.get('directory'):continue
            folder=self.run/v['directory']
            for f in folder.glob('*.json'):
                if f.name!='receipt.json':details.append('### '+stage+'/'+f.name+'\n\n```json\n'+f.read_text()+'```\n')
        report='# TRAINING_READINESS_EXECUTION_REPORT\n\n'+status+'\n\n'+\
          'Training: DISABLED. Dataset: 710 (579/65/66), unchanged. No T01–T15 inspection.\n\n'+\
          'Package SHA-256: '+PACKAGE_SHA+'\n\nModel: '+MODEL+' @ '+REVISION+'\n\n'+\
          '## Gates\n\n```json\n'+json.dumps(result,indent=2)+'\n```\n\n'+\
          '## Interpretation and blockers\n\nRaw first-response capture is not independent model correctness. '+\
          'Semantic review, Docker-only coding validation and full stateful agentic rollouts remain pending. '+\
          'Smoke and fit perform single disposable TRAIN-only optimizer updates, not full training. '+\
          '4096 uses synthetic unlabelled padding for memory measurement; no canonical record is truncated. '+\
          'Session disk survives disconnect/restart, not runtime deletion. Download evidence before losing the runtime. '+\
          'No OOM fallback or automatic sequence reduction. Native versus emulated BF16 must be distinguished. '+\
          'Config VERIFIED means measured feasibility, not tuned quality.\n\n'+\
          '## Environment, identity, acquisition, load, smoke, capture, QLoRA, fit, memory and latency\n\n'+''.join(details)+\
          '\n## Reproducibility / artifacts\n\nSee execution-metadata.json, package-verification.json, '+\
          'training-config-final.json, per-stage receipts, logs, installed versions and artifact-hashes.json.\n'
        (location/'TRAINING_READINESS_EXECUTION_REPORT.md').write_text(report,encoding='utf-8')
        print('\n'+'='*50+'\nSOVEREIGNAI COLAB READINESS\n'+'='*50)
        for label,stage in [('Dataset integrity','integrity'),('Environment','environment'),
                            ('Exact Base acquisition','acquire'),('Base load','base-load'),('Base smoke','base-smoke'),
                            ('Baseline capture','baseline'),('QLoRA smoke','qlora-smoke'),('4096 fit','fit')]:
            print(label+': '+self.stages.get(stage,{}).get('status','NOT_RUN'))
        print('FINAL STATUS:',status,'\nTraining: DISABLED\nNEXT ACTION: download evidence and complete independent baseline review.')

    def export(self):
        location=self.run or self.pending
        save(location/'artifact-hashes.json',{str(f.relative_to(location)):digest(f) for f in location.rglob('*')
             if f.is_file() and f.name!='artifact-hashes.json' and not f.name.endswith('.tmp')})
        archive=self.root.parent/'sovereignai-readiness-actual-evidence'
        shutil.make_archive(str(archive),'zip',location)
        self.archive=archive.with_suffix('.zip')
        print('ARTIFACT:',self.archive,'SHA256:',digest(self.archive))
        return self.archive
