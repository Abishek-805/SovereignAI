"""Read-only registry/baseline audit. Never dispatches generated actions."""
import copy
import hashlib
import json
import sys
from pathlib import Path
from experiments.fidelity_v1.runners import load_native

ROOT = Path(__file__).resolve().parents[2]

def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')

def main():
    out = Path(sys.argv[1])
    native = load_native()
    registry = native.ToolRegistry()
    schemas = registry.schemas()
    save(out/'registry-schemas.json', schemas)
    variants = []
    cases = []
    observations = {}
    for tool in schemas:
        function = tool['function']; name = function['name']; params = function['parameters']
        variants.append({'type':'object', 'properties':{'name':{'type':'string','const':name},'arguments':copy.deepcopy(params)},'required':['name','arguments'],'additionalProperties':False})
        for key, field in params['properties'].items():
            if field['type'] == 'string': observations[name+'.'+key] = []
        valid = {key:('example' if field['type']=='string' else 1) for key,field in params['properties'].items()}
        examples = [('all-fields',valid,True), ('required-only',{key:valid[key] for key in params['required']},True), ('additional-property',{**valid,'unexpected':1},False)]
        for key in params['required']: examples.append(('missing-'+key,{k:v for k,v in valid.items() if k!=key},False))
        for key in valid: examples.append(('wrong-type-'+key,{**valid,key:False},False))
        for label,args,expected in examples:
            encoded=json.dumps({'name':name,'arguments':args}); parsed=json.loads(encoded)
            try: registry.check(parsed['name'],parsed['arguments']); accepted=True
            except ValueError: accepted=False
            cases.append({'name':name,'case':label,'expected':expected,'accepted':accepted,'passed':expected==accepted})
    try: registry.check('unknown',{}); unknown=False
    except ValueError: unknown=True
    cases.append({'case':'unknown-name','passed':unknown})
    schema={'type':'object','properties':{'action':{'oneOf':variants}},'required':['action'],'additionalProperties':False}
    save(out/'action-schema-unbounded.json',schema)
    save(out/'registry-parser-cases.json',cases)
    baseline=ROOT/'evidence/code-agent-fidelity-v1'
    cells=[]; mismatches=[]
    for arm in ('native','nanobot','hermes'):
        for oracle_path in sorted((baseline/arm).glob('T*/attempt-*/post-accept-oracle.json')):
            oracle=json.loads(oracle_path.read_text(encoding='utf-8'))
            if oracle.get('exit_code')!=0 or not oracle.get('container_executed') or not oracle.get('properties') or not all(oracle['properties'].values()): continue
            calls=list(sorted(oracle_path.parent.glob('call-*.json')))
            cells.append({'arm':arm,'task':oracle_path.parent.parent.name,'attempt':oracle_path.parent.name,'oracle':str(oracle_path.relative_to(ROOT)),'calls':len(calls)})
            for call_path in calls:
                call=json.loads(call_path.read_text(encoding='utf-8'))
                if call.get('request',{}).get('tools') != schemas: mismatches.append(str(call_path.relative_to(ROOT)))
                for choice in call.get('response',{}).get('choices',[]):
                    for tool in choice.get('message',{}).get('tool_calls',[]):
                        fn=tool['function']; args=fn['arguments']
                        if isinstance(args,str):
                            try: args=json.loads(args)
                            except ValueError: continue
                        if not isinstance(args,dict): continue
                        for key,value in args.items():
                            identity=fn['name']+'.'+key
                            if identity in observations and isinstance(value,str): observations[identity].append({'value':value,'chars':len(value),'source':str(call_path.relative_to(ROOT))})
    bounds=[]
    for identity,values in observations.items():
        largest=max(values,key=lambda row:row['chars']) if values else None
        bounds.append({'parameter':identity,'observations':len(values),'largest_baseline_value':largest,'margin':256,'derived_maxLength':largest['chars']+256 if largest else None,'source_actions':[row['source'] for row in values],'derivation_formula':'largest observed characters + 256','status':'DERIVED' if largest else 'UNKNOWN'})
    save(out/'baseline-coverage.json',{'successful_cells':cells,'count':len(cells),'schema_mismatches':mismatches,'selection':'independent post-accept Docker oracle exit 0, nonempty all-true properties; every emitted string in selected trajectories included conservatively'})
    save(out/'string-bounds.json',bounds)
    missing=[row['parameter'] for row in bounds if row['status']=='UNKNOWN']
    decision={'registry_actions':[tool['function']['name'] for tool in schemas],'registry_cases_passed':all(case['passed'] for case in cases),'missing_baseline_parameters':missing,'schema_mismatch_count':len(mismatches),'generated_actions_executed':0,'replay_executed':False}
    decision['status']='STOP_SCHEMA_FIDELITY_UNESTABLISHED' if missing or mismatches else 'READY_FOR_CONVERTER_AND_BUDGET_AUDIT'
    save(out/'schema-audit-decision.json',decision)
    print(json.dumps(decision,indent=2))

if __name__=='__main__': main()
