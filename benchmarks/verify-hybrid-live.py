"""Opt-in serial live acceptance on disposable workspaces; no fabricated failures."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('hybrid_live_base', ROOT/'benchmarks/evaluate-smart-code-router-v2.py')
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)
base, shared = v2.base, v2.base.shared


def case(identifier, request, files, active, trusted=None, allowed=None, category='debug'):
    return {'id':identifier,'category':category,'request':request,'complexity':'simple',
            'expected_task_type':'DEBUG','expected_suitable_workers':['code'],
            'allowed_change_paths':allowed or [active],
            'context':{'initial_files':files,'active_file':active},
            'oracle':{'kind':'trusted_tests','trusted_files':{'check.py':trusted},
                      'command':['python','check.py'],'expected_exit_code':0} if trusted else
                     {'kind':'rubric','semantic_review_required':True}}


def fixtures():
    explain = case('explanation','Explain this function.',{'score.py':'def score(values):\n    return sum(values) / len(values) if values else 0\n'},'score.py',category='explanation')
    explain.update(expected_task_type='EXPLAIN',expected_suitable_workers=['lightweight'])
    rename = case('rename','Rename local variable total to subtotal in amount.py. Preserve behavior.',
        {'amount.py':'def amount(items):\n    total = sum(items)\n    return total\n'},'amount.py',
        "import amount\nassert amount.amount([2,3]) == 5\ns=open('amount.py').read()\nassert 'subtotal' in s and '    total =' not in s\n",category='edit')
    repair = case('generated_repair','Fix split_batches in batches.py. Return consecutive lists of at most size items, include the final partial batch, return [] for empty input, and raise ValueError for size <= 0. Preserve input and item order.',
        {'batches.py':'def split_batches(items, size):\n    return [items[i:i+size] for i in range(0, len(items)-size, size)]\n'},'batches.py',
        "from batches import split_batches\nfor n in range(17):\n for size in range(1,7):\n  xs=list(range(n)); before=list(xs)\n  assert split_batches(xs,size)==[xs[i:i+size] for i in range(0,n,size)]\n  assert xs==before\nfor size in [0,-1,-5]:\n try: split_batches([1],size)\n except ValueError: pass\n else: raise AssertionError('nonpositive size')\n")
    complex_case = case('architecture','Refactor the project architecture across catalog.py and billing.py: catalog.py must own a Catalog class with get_price(name), initialized with a price mapping; billing.py must define invoice(names, catalog) returning the sum of catalog prices. Preserve missing-name KeyError and do not duplicate catalog storage in billing. Plan file responsibilities before implementation.',
        {'catalog.py':'def get_price(name, prices):\n    return prices[name]\n','billing.py':'def invoice(names, prices):\n    return sum(prices[n] for n in names)\n'},'billing.py',
        "from catalog import Catalog\nfrom billing import invoice\nc=Catalog({'a':2,'b':5})\nassert invoice(['a','b','a'],c)==9\ntry: invoice(['missing'],c)\nexcept KeyError: pass\nelse: raise AssertionError('missing key')\n",['catalog.py','billing.py'],category='architecture')
    complex_case.update(complexity='complex',expected_task_type='MULTI_FILE')
    warm = case('warm_coder','Update amount.py to return zero for an empty list while preserving the sum for nonempty input.',
        {'amount.py':'def amount(items):\n    return sum(items) if items else None\n'},'amount.py',
        "from amount import amount\nassert amount([])==0\nassert amount([2,3])==5\n",category='edit')
    return explain, rename, repair, complex_case, warm


def servers():
    import psutil
    result=[]
    for process in psutil.process_iter(['pid','name','cmdline']):
        try:
            if (process.info['name'] or '').casefold() in {'llama-server','llama-server.exe'}:
                result.append({'pid':process.pid,'command_sha256':base.digest(process.info['cmdline'] or [])})
        except (psutil.NoSuchProcess,psutil.AccessDenied): pass
    return result


def observed_call(workbench, wid, target, request, args, history=None, cancel_at_generation=False):
    job=shared.BenchmarkJob(args.timeout)
    original_progress=job.progress
    def progress(message,*a,**k):
        original_progress(message,*a,**k)
        if cancel_at_generation and str(message).startswith('Generating '): job.cancel.set()
    job.progress=progress; job.append=progress
    probe=shared.ResourceProbe(True)
    before=servers(); started=time.perf_counter()
    try:
        result=workbench.run_coding_project_task(wid,target,request,job=job,history=history or [])
    except Exception as error:
        result={'error':{'code':getattr(error,'code',type(error).__name__),'message':str(error)}}
    finally:
        job.close(); resources=probe.close()
    snapshots=[]
    for path in (workbench.settings.data_dir/'supervision').glob('*.json'):
        value=json.loads(path.read_text())
        if value.get('goal')==request: snapshots.append(value)
    snapshot=max(snapshots,key=lambda item:item.get('created',0),default={})
    return {'request':request,'operational_result':result,'telemetry':snapshot,
            'measurements':{'latency_seconds':time.perf_counter()-started,**snapshot.get('counts',{}),**resources},
            'server_before':before,'server_after':servers(),'cancelled':job.cancel.is_set()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--timeout',type=float,default=900)
    parser.add_argument('--model-url',default='http://127.0.0.1:8087')
    parser.add_argument('--model-port',type=int,default=8087)
    parser.add_argument('--backend-url',default='http://127.0.0.1:8765')
    parser.add_argument('--backend-job-ids',nargs='*')
    parser.add_argument('--output',type=Path,default=ROOT/'benchmarks/hybrid-live-acceptance.json')
    args=parser.parse_args()
    args.sample_resources=True
    suite=fixtures()
    if not args.live:
        print(json.dumps({'mode':'NOT_EXECUTED','cases':[item['id'] for item in suite]+['follow_up','cancellation','stale_revision'],'fixture_sha256':base.digest(suite)},indent=2)); return
    if args.output.exists(): raise ValueError('Use a fresh output path; previous live evidence is preserved')
    if os.environ.get('SOVEREIGN_KNOWLEDGE_DIR'): raise RuntimeError('Unset SOVEREIGN_KNOWLEDGE_DIR')
    from backend.settings import Settings
    from backend.service import Workbench
    from router.model_registry import ModelRegistry
    from backend.app import create_app
    from fastapi.testclient import TestClient
    settings=Settings(model_url=args.model_url,supervisor_seconds=args.timeout)
    with base.LiveSuiteLock(ROOT/'data/smart-code-router-live.lock'), TemporaryDirectory(prefix='hybrid-live-acceptance-') as temporary:
        idle=base.check_backend_idle(settings,args.backend_url,args.backend_job_ids)
        directory=Path(temporary)
        isolated=Settings(data_dir=directory/'data',project_dir=directory/'projects',model_url=args.model_url,supervisor_seconds=args.timeout)
        isolated.data_dir.mkdir(parents=True)
        shutil.copyfile(settings.data_dir/'sandbox-validation.json',isolated.data_dir/'sandbox-validation.json')
        work=Workbench(settings=isolated,registry=ModelRegistry(args.model_port))
        v2.configure_arm(work,'E')
        work._verified_coding_sandbox()._ready()
        report={'state':'RUNNING','fixture_sha256':base.digest(suite),'backend_idle_check':idle,'rows':[],
                'production_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for d in ['backend','router','workflows'] for p in ROOT.glob(d+'/**/*.py')},
                'limitations':['Sampled process counts do not prove all instants; PIDs captured at boundaries.',
                'Explanation requires independent semantic review; first-pass success does not prove automatic repair.',
                'Private trusted tests are used only by the established independent Docker proxy.',
                'Endpoint calls use actual ASGI routing on this disposable service; no user workspace is accepted.']}
        report['installed_profiles']=[{'registry_key':key,'model_id':profile.identifier,'model_file':profile.model_file,
            'context':profile.context,'revision':profile.revision,'worker_roles':list(profile.worker_roles)} for key,profile in sorted(work.registry.specs.items())]
        report['harness_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        def save(): shared.atomic_report(args.output,report)
        save()
        rows={}
        for item in suite:
            baseline_validation=None
            if item['id']=='generated_repair':
                baseline_validation=base.validate_candidate(item,item['context']['initial_files'],work._verified_coding_sandbox(),min(120,args.timeout))
            before=servers(); row=v2.capture(item,work,args); row['server_before']=before;row['server_after']=servers()
            row['status']='PASS' if row.get('correctness') is True else 'FAIL' if row.get('correctness') is False or row.get('operational_result',{}).get('error') else 'UNKNOWN'
            if item['id']=='explanation':
                row['lightweight_low_call_status']='PASS' if row.get('prediction',{}).get('worker_role')=='lightweight' and row.get('measurements',{}).get('model_calls')==1 else 'NOT_VERIFIED'
            if item['id']=='architecture':
                stages=row.get('routing_observation',{}).get('stages',[])
                roles=[stage.get('worker_role') for stage in stages if stage.get('stage')=='model_selection']
                row['qwen_to_coder_handoff_status']='PASS' if 'reasoning' in roles and 'code' in roles and roles.index('reasoning')<roles.index('code') and row.get('correctness') is True else 'NOT_VERIFIED'
                row['maximum_one_heavy_sampled_status']='PASS' if row.get('measurements',{}).get('max_llama_server_processes')==1 else 'NOT_VERIFIED'
            if item['id']=='generated_repair':
                row['automatic_generated_repair_status']='PASS' if row.get('repair_succeeded') is True else 'NOT_VERIFIED'
                row['baseline_validation']=baseline_validation
                row['baseline_broken_source_is_not_generated_failure']=True
            if item['id']=='warm_coder':
                row['warm_affinity_status']='PASS' if before and row.get('server_after')==before and row.get('measurements',{}).get('model_switches')==0 else 'FAIL'
            rows[item['id']]=row; report['rows'].append(row);save()
            if row.get('gate')=='STOP': report['state']='STOPPED';save();return
        repair=suite[2]; prior=rows['generated_repair']['operational_result'];wid=prior.get('workspace_id')
        if wid:
            history=['user: '+repair['request']]
            follow=[]
            for request in ['fix that','now make the tests pass']:
                row=observed_call(work,wid,repair['context']['active_file'],request,args,history)
                state=row.get('telemetry',{}).get('task_state',{})
                row['scope_preserved']=state.get('workspace')==wid and state.get('target')==repair['context']['active_file']
                row['previous_task_observed']=bool((state.get('follow_up_context') or {}).get('previous_task_id'))
                follow.append(row);history=['user: '+request]
            report['rows'].append({'case_id':'follow_up','status':'PASS' if all(x['scope_preserved'] and x['previous_task_observed'] for x in follow) else 'FAIL','turns':follow})
        else: report['rows'].append({'case_id':'follow_up','status':'NOT_VERIFIED','reason':'No preceding observed repair workspace'})
        save()
        cancel_ws=work.coding.create('live-cancellation')['workspace_id'];work.coding.write(cancel_ws,'cancel.py','def value():\n    return 1\n')
        original=work.coding.raw_files(cancel_ws)
        cancelled=observed_call(work,cancel_ws,'cancel.py','Update cancel.py to return 2.',args,cancel_at_generation=True)
        cancelled.update(case_id='cancellation',source_preserved=work.coding.raw_files(cancel_ws)==original)
        cancelled['status']='PASS' if cancelled['source_preserved'] and cancelled['operational_result'].get('error',{}).get('code')=='cancelled' else 'FAIL'
        report['rows'].append(cancelled);save()
        staged=next((row for key,row in rows.items() if key!='explanation' and row.get('correctness') is True and row['operational_result'].get('publication_state')=='staged'),None)
        if staged:
            result=staged['operational_result'];wid=result['workspace_id'];task_id=result['task_id']
            selected=next(change for change in result['changes'] if change['action'] in {'create','edit'})
            work.coding.write(wid,selected['path'],'# external revision intentionally changed\n')
            changed=work.coding.raw_files(wid)
            client=TestClient(create_app(work),base_url='http://127.0.0.1')
            response=client.post('/coding/workspaces/'+wid+'/tasks/'+task_id+'/accept')
            report['rows'].append({'case_id':'stale_revision','status':'PASS' if response.status_code>=400 and response.json().get('code')=='workspace_conflict' and work.coding.raw_files(wid)==changed else 'FAIL',
                'http_status':response.status_code,'response':response.json(),'source_preserved':work.coding.raw_files(wid)==changed,
                'endpoint':'POST /coding/workspaces/{workspace_id}/tasks/{task_id}/accept','workspace_is_disposable':True})
        else:report['rows'].append({'case_id':'stale_revision','status':'NOT_VERIFIED','reason':'No independently validated staged candidate available'})
        publishable=next((row for row in rows.values() if row is not staged and row.get('correctness') is True and row['operational_result'].get('publication_state')=='staged'),None)
        if publishable:
            result=publishable['operational_result'];wid=result['workspace_id'];task_id=result['task_id']
            candidate={change['path']:change['after'].encode() for change in result['changes'] if change['action'] in {'create','edit'}}
            client=TestClient(create_app(work),base_url='http://127.0.0.1')
            response=client.post('/coding/workspaces/'+wid+'/tasks/'+task_id+'/accept')
            actual=work.coding.raw_files(wid)
            report['publication_acceptance']={'status':'PASS' if response.status_code==200 and all(actual.get(name)==data for name,data in candidate.items()) else 'FAIL',
                'http_status':response.status_code,'exact_candidate_hashes':{name:hashlib.sha256(data).hexdigest() for name,data in candidate.items()},
                'response':response.json(),'endpoint':'POST /coding/workspaces/{workspace_id}/tasks/{task_id}/accept','workspace_is_disposable':True}
        else: report['publication_acceptance']={'status':'NOT_VERIFIED','reason':'No second independently validated staged candidate'}
        report['state']='COMPLETED';save()
        print(json.dumps({'state':report['state'],'statuses':[{k:row.get(k) for k in ['case_id','status','automatic_generated_repair_status']} for row in report['rows']]},indent=2))

if __name__=='__main__': main()
