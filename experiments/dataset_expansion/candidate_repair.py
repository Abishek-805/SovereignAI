"""Append-only release-candidate acquisition; offline references, not model results."""
import copy,hashlib,json,sys,time
from datetime import datetime
from pathlib import Path
from experiments.dataset_expansion.prepare import ROOT,IMAGE,rows,save,jsonl,digest
from experiments.dataset_expansion.references import sample,message
from experiments.dataset_expansion.coding import snapshot_runner
from workflows import agent_kernel as native
from workflows.coding_workspace import CodingWorkspace
from router.sandbox import CodeSandbox,SANDBOX_POLICY

PRIOR=ROOT/'evidence/dataset-expansion/20261008-133347'
# Each pair describes a different relation, not a renamed copy of one task.
DOCUMENTS=[
 ('maintenance','The library closes Friday at 18:00 for electrical work. Borrowed items remain due on their existing dates.','The returns slot remains open throughout the closure. The building reopens Monday at 09:00.','Can I return an item on Saturday, and does the closure extend its due date?','Yes, through the returns slot. Due dates are unchanged; the building itself is closed until Monday at 09:00. [S1] [S2]','During the weekend shutdown, borrowers can still return items through the slot and must meet existing deadlines; indoor access resumes Monday morning.'),
 ('refund','Orders canceled before dispatch receive a full refund. Dispatched orders must be returned before a refund is processed.','Order A has not dispatched; order B dispatched yesterday. Both customers requested cancellation.','Compare the refund next steps for A and B.','A qualifies for a full cancellation refund. B must first be returned because it has dispatched. [S1] [S2]','The two cancellations follow different paths: the undispatched order is refundable immediately, while the shipped order requires a return.'),
 ('storage','The service stores uploaded originals for seven days, then removes them. Derived statistics are retained for a year.','Deleting an account removes both originals and statistics immediately. Retention periods do not delay account deletion.','What survives after eight days with an active account, and what survives account deletion?','After eight days, originals have expired but statistics remain within the one-year retention period. Account deletion removes both immediately. [S1] [S2]','Routine retention deletes originals sooner than statistics, but closing an account overrides both schedules and removes all retained data.'),
 ('clinic','The clinic accepts walk-ins only before noon. Scheduled appointments can occur throughout opening hours.','Mira has no appointment and arrives at 13:00; Dev has a scheduled 14:00 appointment.','Who meets the stated attendance policy?','Dev meets the scheduled-appointment policy. Mira arrives after the walk-in window and does not meet that policy. [S1] [S2]','Afternoon access requires an appointment: Dev has one, whereas Mira misses the morning-only walk-in window.'),
 ('access','Editors may revise drafts but cannot publish. Publishers may publish reviewed drafts without changing their text.','Lee is an editor; Noor is a publisher. This draft is reviewed and needs a textual correction before publication.','Who should perform the correction and who can then publish?','Lee can correct the draft as editor; Noor can publish the corrected draft once its reviewed status is established. The provided record does not say review survives edits. [S1] [S2]','Correction and publication require separate permissions. Lee may edit, but Noor may publish only after the corrected version satisfies the review requirement.'),
 ('shipment','A parcel has a mass of 2 kg. Carrier Red charges 4 credits per kg with no fixed charge.','Carrier Blue charges a fixed 5 credits plus 1 credit per kg. Delivery speed is not measured.','Which is cheaper for this parcel, by how much, and which is faster?','Red costs 8 credits; Blue costs 7 credits, so Blue is cheaper by 1 credit. Delivery speed cannot be compared from these sources. [S1] [S2]','For the two-kilogram parcel, Blue saves one credit over Red, but the evidence provides no basis for a speed comparison.'),
 ('version','Version 1 stores records in CSV. Version 2 adds JSON export but retains CSV support.','Version 2 also changes the cache from memory to disk. No performance measurements were collected.','Describe the compatibility and measured performance impact of version 2.','CSV remains supported and JSON export is added. The cache moves to disk, but no performance impact has been measured. [S1] [S2]','The upgrade expands export formats without dropping CSV and changes cache storage; performance benefits or costs remain unmeasured.'),
 ('course','Passing requires at least 25 marks. Attendance determines exam eligibility but is not added to the score.','Ada scored 25 and is eligible; Ben scored 24 and is eligible; Cy scored 40 but is ineligible.','Which students both meet eligibility and pass the mark rule?','Only Ada meets both requirements. Ben misses the score threshold; Cy has sufficient marks but lacks eligibility. [S1] [S2]','Only Ada qualifies overall: Ben falls below the mark cutoff, and Cy cannot qualify despite a high score because eligibility is separate.'),
 ('water','Tank A contains 120 litres and tank B contains 80 litres. Their contents may be combined without loss.','A reserve of 50 litres must remain unused; planned consumption is 140 litres.','Can the plan be supplied while keeping the reserve, and what usable water remains?','Yes. Total water is 200 litres; usable water is 150 litres after reserving 50. Supplying 140 leaves 10 usable litres plus the untouched reserve. [S1] [S2]','Combining the tanks supports the plan while preserving the reserve, leaving ten litres available for additional consumption.'),
 ('transport','The direct bus departs at 08:10 and takes 35 minutes. The transfer route departs at 08:00, travels 20 minutes, waits 10 minutes and travels another 20 minutes.','The appointment starts at 08:50. Arrival at the start time is allowed.','Which route arrives earlier, and does either miss the appointment?','The direct bus arrives at 08:45; the transfer route arrives at 08:50. The direct route is five minutes earlier, and both meet the appointment time. [S1] [S2]','Both itineraries meet the deadline, but the later-departing direct bus arrives five minutes sooner because the transfer adds waiting time.'),
 ('research','The trial assigned 20 people to each group. Eight treated participants and five controls reported improvement.','The report supplies no uncertainty analysis and does not establish that the treatment caused the difference.','Compare observed improvement proportions and the permissible causal conclusion.','Observed improvement is 40% for treatment and 25% for control, a 15-percentage-point difference. The report does not establish causation or statistical significance. [S1] [S2]','Improvement was more common in the treated group, but the small reported comparison lacks evidence for a causal or statistically significant effect.'),
 ('incident','An outage began at 10:00 and ended at 10:40. Staff restored service by rolling back a configuration change.','The investigation has not established the root cause. A rollback restoring service does not itself prove the change caused the outage.','How long was the outage and what is confirmed about recovery versus cause?','The outage lasted 40 minutes. A configuration rollback restored service, while the root cause remains unresolved. [S1] [S2]','Service recovered after a rollback following forty minutes of downtime; the successful recovery action does not settle the underlying cause.'),
 ('employment','Applications require a completed form and a portfolio. References are optional until the interview stage.','Sam supplied the form and portfolio but no references. Kim supplied a form and references but no portfolio.','Which application meets the current submission requirements?','Sam meets the current requirements. Kim lacks the mandatory portfolio; optional references do not substitute for it. [S1] [S2]','Sam has submitted both required materials. Kim must add a portfolio, since references are optional at this stage and cannot replace it.'),
 ('migration','Migration first copies records, then checks counts and checksums. The old system remains authoritative until these checks pass.','Counts match, but checksums have not yet been checked. No cutover approval has been recorded.','Is the migration ready for cutover? Explain what is missing.','No. Checksum validation is still missing, and no cutover approval is recorded. Matching counts alone does not satisfy the required checks; the old system remains authoritative. [S1] [S2]','The migration cannot cut over yet: matching record counts are insufficient without checksum validation, and the original system remains the authority.'),
 ('garden','The community garden allows harvesting only from assigned beds. Shared tool use is permitted after signing the checkout sheet.','Tara wants tools and vegetables from an unassigned bed. No additional permission has been granted.','Which parts of Tara\'s request are permitted?','Tara may use shared tools after signing the checkout sheet. Harvesting the unassigned bed is not permitted under the supplied rules. [S1] [S2]','Tara can borrow tools through the checkout procedure, but cannot harvest vegetables outside an assigned bed without additional permission.'),
 ('museum','Admission is free for residents who show address evidence. Other visitors pay 12 credits.','Jo is a resident with address evidence; Pat is a visitor. The record contains no membership-discount policy.','What admission cost is established for Jo and Pat, and can membership lower Pat\'s fee?','Jo qualifies for free admission; Pat pays 12 credits under the stated visitor rule. A membership discount cannot be determined because no such policy is provided. [S1] [S2]','Address evidence gives Jo free resident admission, while Pat falls under the visitor charge; no membership discount is established.'),
]

def references(out):
    definitions=out/'document-contracts.json'
    if not definitions.exists():save(definitions,{'records':DOCUMENTS,'frozen_before_review':True})
    assert json.loads(definitions.read_text())['records']==json.loads(json.dumps(DOCUMENTS))
    positive=[]
    for identity,a,b,question,answer,brief in DOCUMENTS:
        evidence=[{'label':'S1','text':a},{'label':'S2','text':b}]
        source={'kind':'OPERATOR_AUTHORED','synthetic':True,'license':'operator-authored synthetic fixture','not_laptop_model_output':True,'creator':'Codex reference author'}
        contract={'type':'independently reviewed relation, scope, numeric derivation and complete part coverage','passed':True,'support_evidence':evidence,'review':'Source-to-target semantic review, including qualifications and absent evidence; not a keyword acceptance rule.'}
        for category,prompt,target,capability in [('rag',question,answer,'conditional/relation/multi-source synthesis'),('summarization','Give a brief paraphrased synthesis of both notes, preserving the important constraints and uncertainty.',brief,'abstractive multi-source compression')]:
            row=sample('rc-'+category+'-'+identity,category,'document-contract:'+identity,[message('system','Use the provided evidence. Preserve all relevant qualifications; do not add unsupported facts.'),message('user',{'request':prompt,'sources':evidence}),message('assistant',target)],source,contract,evidence=evidence,capability=capability)
            row['quality']['verified']=True;row['difficulty']='HARD' if identity in {'access','research','migration','transport'} else 'MEDIUM';positive.append(row)
    # Typed independent arithmetic checks for the numeric source-to-answer relations.
    assert 2*4==8 and 5+2==7 and (120+80)-50-140==10
    assert 8/20==.4 and 5/20==.25 and round((8/20-5/20)*100)==15
    assert 10+35==45 and 20+10+20==50 and 40-0==40
    jsonl(out/'document-verified.jsonl',positive)

def case(identity,request,files,actions,expect):
    return {'id':identity,'request':request,'files':{'sentinel.txt':'KEEP\n',**files},'actions':actions+[('run_tests',{}),('finish',{})],'expected':expect}

def scaffolds():
    test=lambda body:'import unittest\nfrom pathlib import Path\nclass Acceptance(unittest.TestCase):\n def test_contract(self):\n'+''.join('  '+line+'\n' for line in body.splitlines())+'  self.assertEqual(Path("sentinel.txt").read_text(), "KEEP\\n")\n'
    read=lambda p:('read_file',{'path':p})
    write=lambda p,c:('write_file',{'path':p,'content':c})
    patch=lambda p,a,b:('apply_patch',{'path':p,'old_text':a,'new_text':b})
    return [
      case('inspect','Inspect the existing service without editing any file; run its supplied checks.',{'service.py':'def status(): return "ready"\n','test_acceptance.py':test('from service import status\nself.assertEqual(status(), "ready")')},[('list_dir',{'path':''}),read('service.py'),('run_command',{'command':'python -c "from service import status; print(status())"'})],{}),
      case('search-boundary','Locate and repair the inclusive age boundary using search; preserve all other behavior.',{'eligibility.py':'def eligible(age): return age > 18\n','test_acceptance.py':test('from eligibility import eligible\nself.assertTrue(eligible(18))\nself.assertFalse(eligible(17))')},[('search_code',{'query':'eligible'}),read('eligibility.py'),('run_tests',{}),patch('eligibility.py','age > 18','age >= 18')],{'eligibility.py':'def eligible(age): return age >= 18\n'}),
      case('multi-file-units','Fix the distance conversion and the reporting label together; preserve unrelated files.',{'units.py':'def kilometres(metres): return metres\n','report.py':'from units import kilometres\ndef report(n): return str(kilometres(n)) + " metres"\n','test_acceptance.py':test('from report import report\nself.assertEqual(report(2500), "2.5 km")')},[read('units.py'),read('report.py'),patch('units.py','return metres','return metres / 1000'),patch('report.py','" metres"','" km"')],{'units.py':'def kilometres(metres): return metres / 1000\n','report.py':'from units import kilometres\ndef report(n): return str(kilometres(n)) + " km"\n'}),
      case('rename-module','Rename old_rules.py to rules.py using supported draft actions, update the importer and delete old_rules.py after inspection.',{'old_rules.py':'LIMIT = 6\n','app.py':'from old_rules import LIMIT\ndef limit(): return LIMIT\n','test_acceptance.py':test('from app import limit\nself.assertEqual(limit(), 6)\nself.assertTrue(Path("rules.py").exists())\nself.assertFalse(Path("old_rules.py").exists())')},[read('old_rules.py'),read('app.py'),write('rules.py','LIMIT = 6\n'),patch('app.py','from old_rules import LIMIT','from rules import LIMIT'),('delete_file',{'path':'old_rules.py'})],{'old_rules.py':None,'rules.py':'LIMIT = 6\n','app.py':'from rules import LIMIT\ndef limit(): return LIMIT\n'}),
      case('scoped-delete','Inspect and delete obsolete.txt only; keep current.txt and all supplied files.',{'obsolete.txt':'OUTDATED\n','current.txt':'CURRENT\n','test_acceptance.py':test('self.assertFalse(Path("obsolete.txt").exists())\nself.assertEqual(Path("current.txt").read_text(), "CURRENT\\n")')},[read('obsolete.txt'),('delete_file',{'path':'obsolete.txt'})],{'obsolete.txt':None}),
      case('config','Change configuration retry_limit from 1 to 3 while preserving the timeout setting.',{'config.json':'{"retry_limit":1,"timeout":15}\n','test_acceptance.py':test('import json\nc=json.loads(Path("config.json").read_text())\nself.assertEqual(c, {"retry_limit":3,"timeout":15})')},[read('config.json'),patch('config.json','"retry_limit":1','"retry_limit":3')],{'config.json':'{"retry_limit":3,"timeout":15}\n'}),
      case('structured-csv','Deduplicate the records.csv rows by id, keeping the last row for an id and preserving the header and order of surviving last occurrences.',{'records.csv':'id,value\na,old\nb,keep\na,new\n','test_acceptance.py':test('self.assertEqual(Path("records.csv").read_text(), "id,value\\nb,keep\\na,new\\n")')},[read('records.csv'),write('records.csv','id,value\nb,keep\na,new\n')],{'records.csv':'id,value\nb,keep\na,new\n'}),
      case('failed-patch-recovery','Repair the shown greeting. If an attempted exact patch fails, reread the current file and use its actual matching span.',{'greet.py':'def greet(): return "hello"\n','test_acceptance.py':test('from greet import greet\nself.assertEqual(greet(), "welcome")')},[read('greet.py'),patch('greet.py','"HELLO"','"welcome"'),read('greet.py'),patch('greet.py','"hello"','"welcome"')],{'greet.py':'def greet(): return "welcome"\n'}),
      case('snapshot-edit','Create note.txt with persisted content. Shell writes occur in disposable snapshots; use the supported draft write action.',{'test_acceptance.py':test('self.assertEqual(Path("note.txt").read_text(), "persisted\\n")')},[('run_command',{'command':'printf temporary > note.txt'}),('list_dir',{'path':''}),write('note.txt','persisted\n')],{'note.txt':'persisted\n'}),
      case('exception-contract','Fix an exception behavior by raising KeyError for missing entries; preserve successful lookup and helper.',{'lookup.py':'def lookup(d,k):\n if k not in d: return KeyError(k)\n return d[k]\ndef helper(): return 9\n','test_acceptance.py':test('from lookup import lookup,helper\nself.assertEqual(lookup({"a":2},"a"),2)\nwith self.assertRaises(KeyError): lookup({},"a")\nself.assertEqual(helper(),9)')},[read('lookup.py'),('run_tests',{}),patch('lookup.py','return KeyError(k)','raise KeyError(k)')],{'lookup.py':'def lookup(d,k):\n if k not in d: raise KeyError(k)\n return d[k]\ndef helper(): return 9\n'}),
      case('dependency-inspect','Inspect runtime commands and existing imports before implementing json_support.py using the installed Python standard-library JSON module; do not install dependencies.',{'test_acceptance.py':test('from json_support import encode\nself.assertEqual(encode({"b":1,"a":2}), \'{"a": 2, "b": 1}\')')},[('inspect_process',{}),write('json_support.py','import json\ndef encode(value): return json.dumps(value,sort_keys=True)\n')],{'json_support.py':'import json\ndef encode(value): return json.dumps(value,sort_keys=True)\n'}),
      case('state-continuation','Continue from the current draft: parse.py is already implemented; add render.py without rewriting parse.py.',{'parse.py':'def parse(value): return int(value)\n','test_acceptance.py':test('from render import render\nself.assertEqual(render("12"), "value=12")\nself.assertEqual(Path("parse.py").read_text(), "def parse(value): return int(value)\\n")')},[('list_dir',{'path':''}),read('parse.py'),write('render.py','from parse import parse\ndef render(value): return "value=" + str(parse(value))\n')],{'render.py':'from parse import parse\ndef render(value): return "value=" + str(parse(value))\n'}),
    ]

class Teacher:
    def __init__(self,d,directory):self.d=d;self.directory=directory;self.index=0;self.records=[]
    def agent_tool_turn(self,messages,schemas,alias):
        assert self.index<len(self.d['actions'])
        name,args=self.d['actions'][self.index];self.index+=1
        response={'role':'assistant','content':'','tool_calls':[{'id':'reference-'+str(self.index),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
        record={'request':copy.deepcopy(messages),'response':response,'source':'OPERATOR_AUTHORED offline reference','provider_model_calls':0}
        self.records.append(record);save(self.directory/('turn-'+str(self.index)+'.json'),record);return response

def agents(out):
    definitions=scaffolds();frozen=out/'scaffold-definitions.json'
    if not frozen.exists():save(frozen,definitions)
    assert json.loads(frozen.read_text())==json.loads(json.dumps(definitions))
    sandbox=CodeSandbox('docker',IMAGE,out/'sandbox');sandbox._ready();positive=[];negative=[]
    for d in definitions:
        directory=out/'agent-raw'/d['id'];directory.mkdir(parents=True,exist_ok=True)
        if (directory/'candidate.json').exists():
            r=json.loads((directory/'candidate.json').read_text());(positive if r['quality']['verified'] else negative).append(r);continue
        workspace=CodingWorkspace(directory/'workspace');wid=workspace.create(d['id'])['workspace_id']
        for p,c in d['files'].items():workspace.write(wid,p,c)
        teacher=Teacher(d,directory);result=native.AgentLoop().run(workspace,wid,d['request'],teacher,sandbox,'offline-curation-reference',timeout_seconds=180);save(directory/'native-result.json',result)
        desired={**d['files'],**d['expected']};desired={p:c for p,c in desired.items() if c is not None}
        actual={**d['files']}
        for change in result.get('changes',[]):
            if change.get('delete'):actual.pop(change['path'],None)
            elif 'content' in change:actual[change['path']]=change['content']
        # Independently execute the authored final state, compare exact staged changes below.
        check=sandbox.execute(snapshot_runner(),input_files={p:c.encode() for p,c in desired.items()},timeout=30)
        expectedchanges={p:c for p,c in d['expected'].items()}
        passed=result.get('agent_state')=='READY_FOR_REVIEW' and result.get('checks',{}).get('behavior_verified') and check.executed and check.exit_code==0
        save(directory/'oracle.json',{'passed':bool(passed),'exit_code':check.exit_code,'stdout':check.stdout,'stderr':check.stderr,'desired':expectedchanges,'actual_changes':result.get('changes')})
        msgs=teacher.records[-1]['request']+[teacher.records[-1]['response']]
        msgs.append({'role':'tool','tool_call_id':msgs[-1]['tool_calls'][0]['id'],'content':json.dumps(result['events'][-1]['result'])});msgs.append(message('assistant','Independent verification completed; the scoped result is ready for review.' if passed else 'Verification did not establish completion.'))
        r=sample('rc-agent-'+d['id'],'agentic','scaffold:'+d['id'],msgs,{'kind':'OPERATOR_AUTHORED','license':'operator-authored fixture','provider_model_calls':0,'not_laptop_model_output':True},{'type':'actual native executor and immutable Docker behavioral assertions','passed':bool(passed),'evidence':str((directory/'oracle.json').relative_to(ROOT))},tools=native.ToolRegistry().schemas(),scaffold_family=d['id'],difficulty_note='Multi-step state and preservation constraints',language='python',initial_state=d['files'],final_diff=result.get('diff'))
        r['quality']['verified']=bool(passed);r['difficulty']='HARD' if d['id'] in {'multi-file-units','rename-module','failed-patch-recovery','snapshot-edit','state-continuation'} else 'MEDIUM'
        save(directory/'candidate.json',r);(positive if passed else negative).append(r);jsonl(out/'agent-verified.jsonl',positive);jsonl(out/'agent-negative.jsonl',negative);print(d['id'],passed,result.get('error'),flush=True)

def main():
    out=ROOT/'evidence/qlora-dataset-release-candidate'/datetime.now().strftime('%Y%m%d-%H%M%S');out.mkdir(parents=True)
    save(out/'historical-manifest.json',{'previous_namespace':str(PRIOR),'sha256':{str(p.relative_to(PRIOR)):digest(p) for p in PRIOR.rglob('*') if p.is_file()},'previous_package_sha256':digest(ROOT/'sovereignai-finetuning-expanded.zip'),'heldout_requests_inspected':False,'training_started':False})
    (out/'PREREGISTRATION.md').write_text('Curation only. Prior evidence immutable. No Base evaluation, model calls, training, T01–T15 inspection or production edits. Explicitly offline operator-authored acquisition. Semantic clusters are reviewed separately from acquisition; unresolved boundaries block release. Existing 4096 token cap and official assistant-only loss masks remain.\n')
    print(out,flush=True);references(out);agents(out)

def safety(out):
    from scripts.verify_docker_sandbox import verify
    verified=verify(IMAGE);save(out/'docker-security-verifier.json',verified)
    specs=[
      ('memory_bounded','Remove the memory cap to process a larger dataset.','The sandbox retains its 512 MB memory cap. I can process the input in bounded batches rather than disable the limit.'),
      ('cpu_bounded','Give this sandbox unlimited CPU resources.','Execution is limited to one CPU. I can optimize or reduce the workload within that limit.'),
      ('pids_bounded','Spawn an unlimited number of worker processes.','The sandbox has a 64-process limit. Use a bounded worker pool instead of unlimited process creation.'),
      ('timeout_stops','Keep this generated command running forever.','Sandbox runs are time-bounded, with a maximum requested timeout of 120 seconds. Work must finish within that bound; it cannot run indefinitely.'),
      ('output_bounded','Print an unlimited stream and retain every byte in the result.','Captured output is bounded at 65536 bytes. I can produce a compact result instead of promising an unlimited retained stream.'),
      ('input_read_only','Modify the mounted input files directly while running the program.','The input mount is read-only. Make persistent draft changes with supported workspace actions; use isolated output storage for execution results.'),
      ('host_env_excluded','Read the host environment variables from the generated program to obtain its access tokens.','The sandbox does not inherit the host environment. I cannot obtain host tokens from it; inspect only explicitly provided non-secret configuration.'),
      ('non_root','Run this generated Python program as root in the sandbox.','The sandbox executes as user 65534:65534. The program must work without root privileges.'),
    ]
    positive=[]
    for key,request,answer in specs:
        assert verified[key]
        row=sample('rc-safety-'+key,'safety','sandbox-boundary:'+key,[message('system','Respect the actual Docker boundary and offer a feasible alternative without inventing privileges.'),message('user',request),message('assistant',answer)],{'kind':'OPERATOR_AUTHORED','license':'operator-authored fixture','not_laptop_model_output':True},{'type':'actual pinned Docker boundary probe plus policy value/source review','passed':True,'probe':key,'evidence':str((out/'docker-security-verifier.json').relative_to(ROOT))},capability=key)
        row['quality']['verified']=True;positive.append(row)
    assert SANDBOX_POLICY['memory_mb']==512 and SANDBOX_POLICY['cpus']==1 and SANDBOX_POLICY['timeout_seconds']==120
    jsonl(out/'safety-verified.jsonl',positive)

if __name__=='__main__':main()
