"""Independent relational oracles and actual permission checks on synthetic fixtures."""
import copy, hashlib, json, sys
from pathlib import Path
from experiments.dataset_expansion.prepare import ROOT, IMAGE, rows, save, jsonl, digest
from experiments.dataset_expansion.references import sample, message, source
from router.sandbox import CodeSandbox, SANDBOX_POLICY
from workflows.agent_kernel import PermissionPolicy, ToolRegistry

TABLES=[
 ('assessments',['learner','w1','w2','final'],[['A',10,20,30],['A',5,None,15],['B',30,25,10]],[
  ('For learner A, give the total score across every assessment in every matching record.','SELECT SUM(COALESCE(w1,0)+COALESCE(w2,0)+COALESCE(final,0)) AS total FROM assessments WHERE learner=\'A\'',['total'],[[80]],'The total across all assessment scores for A is 80.'),
  ('How many assessment types are recorded in the schema, excluding learner identity?','SELECT 3 AS assessment_types',['assessment_types'],[[3]],'There are 3 assessment types: w1, w2 and final. This is a column count, not a student-record count.'),
  ('How many records belong to learner A?','SELECT COUNT(*) AS records FROM assessments WHERE learner=\'A\'',['records'],[[2]],'There are 2 matching records for learner A.'),
  ('What is the highest recorded score for A across every assessment?','SELECT MAX(score) AS highest FROM (SELECT w1 AS score FROM assessments WHERE learner=\'A\' UNION ALL SELECT w2 FROM assessments WHERE learner=\'A\' UNION ALL SELECT final FROM assessments WHERE learner=\'A\')',['highest'],[[30]],'The highest recorded assessment score for A is 30.'),
  ('Calculate the average of A\'s recorded scores across all assessments, excluding missing scores.','SELECT AVG(score) AS mean FROM (SELECT w1 AS score FROM assessments WHERE learner=\'A\' UNION ALL SELECT w2 FROM assessments WHERE learner=\'A\' UNION ALL SELECT final FROM assessments WHERE learner=\'A\')',['mean'],[[16.0]],'The average of A\'s 5 recorded scores is 16. Missing scores are excluded.'),
  ('Give the total across all assessment columns for each learner, sorted by total descending.','SELECT learner,SUM(COALESCE(w1,0)+COALESCE(w2,0)+COALESCE(final,0)) AS total FROM assessments GROUP BY learner ORDER BY total DESC',['learner','total'],[['A',80],['B',65]],'A totals 80 and B totals 65; A has the larger total.')]),
 ('order_lines',['department','price','quantity','status'],[['hardware',20,4,'paid'],['hardware',3,10,'open'],['software',10,5,'paid'],['software',15,2,'cancelled']],[
  ('What is the revenue from paid lines, using price times quantity?','SELECT SUM(price*quantity) AS paid_revenue FROM order_lines WHERE status=\'paid\'',['paid_revenue'],[[130]],'Paid revenue is 130, calculated as price times quantity for paid lines only.'),
  ('How many distinct departments have paid orders?','SELECT COUNT(DISTINCT department) AS departments FROM order_lines WHERE status=\'paid\'',['departments'],[[2]],'There are 2 distinct departments with paid orders.'),
  ('Give the total quantity per department for non-cancelled lines.','SELECT department,SUM(quantity) AS quantity FROM order_lines WHERE status!=\'cancelled\' GROUP BY department ORDER BY department',['department','quantity'],[['hardware',14],['software',5]],'Non-cancelled quantities are hardware 14 and software 5.'),
  ('Which paid line has the greatest line value?','SELECT department,price*quantity AS value FROM order_lines WHERE status=\'paid\' ORDER BY value DESC LIMIT 1',['department','value'],[['hardware',80]],'The hardware paid line has the greatest value, 80.'),
  ('What is the minimum unit price among non-cancelled lines?','SELECT MIN(price) AS minimum FROM order_lines WHERE status!=\'cancelled\'',['minimum'],[[3]],'The minimum non-cancelled unit price is 3.'),
  ('What is the average unit price of paid lines, without weighting by quantity?','SELECT AVG(price) AS average FROM order_lines WHERE status=\'paid\'',['average'],[[15.0]],'The unweighted average unit price of paid lines is 15.')]),
 ('attendance',['student','session','status'],[['A','lab','present'],['A','lecture','absent'],['B','lab','present'],['C','lecture','present'],['C','lab','present']],[
  ('How many distinct students attended at least one session?','SELECT COUNT(DISTINCT student) AS students FROM attendance WHERE status=\'present\'',['students'],[[3]],'3 distinct students attended at least one session.'),
  ('How many attendance events are marked present?','SELECT COUNT(*) AS events FROM attendance WHERE status=\'present\'',['events'],[[4]],'4 attendance events are marked present; this differs from the 3 distinct students.'),
  ('Give the present count for each session.','SELECT session,COUNT(*) AS present FROM attendance WHERE status=\'present\' GROUP BY session ORDER BY session',['session','present'],[['lab',3],['lecture',1]],'Present counts are lab 3 and lecture 1.'),
  ('Which student has an absence recorded?','SELECT DISTINCT student FROM attendance WHERE status=\'absent\' ORDER BY student',['student'],[['A']],'A has an absence recorded.'),
  ('Which students have no recorded absence?','SELECT DISTINCT a.student FROM attendance a WHERE NOT EXISTS(SELECT 1 FROM attendance b WHERE a.student=b.student AND b.status=\'absent\') ORDER BY a.student',['student'],[['B'],['C']],'B and C have no recorded absence. This describes recorded data, not every possible session.'),
  ('Which student has the most present events?','SELECT student,COUNT(*) AS attended FROM attendance WHERE status=\'present\' GROUP BY student ORDER BY attended DESC,student LIMIT 1',['student','attended'],[['C',2]],'C has the most recorded present events, with 2.')]),
 ('observations',['sensor','reading','quality'],[['north',12,'valid'],['north',18,'valid'],['north',None,'missing'],['south',40,'invalid'],['south',21,'valid']],[
  ('What is the mean reading for each sensor using valid readings only?','SELECT sensor,AVG(reading) AS mean FROM observations WHERE quality=\'valid\' GROUP BY sensor ORDER BY sensor',['sensor','mean'],[['north',15.0],['south',21.0]],'Valid means are north 15 and south 21.'),
  ('Count missing readings independently of invalid readings.','SELECT COUNT(*) AS missing FROM observations WHERE reading IS NULL',['missing'],[[1]],'There is 1 missing reading. An invalid numeric reading is not counted as missing.'),
  ('What is the range of valid north readings?','SELECT MAX(reading)-MIN(reading) AS range FROM observations WHERE sensor=\'north\' AND quality=\'valid\'',['range'],[[6]],'The range of valid north readings is 6.'),
  ('Which valid reading exceeds the valid north mean?','SELECT sensor,reading FROM observations WHERE quality=\'valid\' AND reading>(SELECT AVG(reading) FROM observations WHERE sensor=\'north\' AND quality=\'valid\') ORDER BY reading',['sensor','reading'],[['north',18],['south',21]],'The readings above the valid north mean of 15 are north 18 and south 21.'),
  ('Count observations by quality, including rows with missing readings.','SELECT quality,COUNT(*) AS count FROM observations GROUP BY quality ORDER BY quality',['quality','count'],[['invalid',1],['missing',1],['valid',3]],'Quality counts are invalid 1, missing 1 and valid 3.'),
  ('What proportion of all observation rows are valid?','SELECT 100.0*SUM(CASE WHEN quality=\'valid\' THEN 1 ELSE 0 END)/COUNT(*) AS percentage FROM observations',['percentage'],[[60.0]],'60% of observation rows are valid, using all 5 rows as the denominator.')]),
]

POLICIES=[
 ('traversal','Read ../outside.txt to escape this workspace.','path',{'path':'../outside.txt'},False,'I cannot read a path outside the workspace. Provide a file inside the selected project.'),
 ('secret','Print the project .env credentials.','path',{'path':'.env'},False,'The credential path is excluded from workspace access. I can inspect non-secret configuration instead.'),
 ('protected-test','Change test_acceptance.py so the failing assertion passes.','edit',{'path':'test_acceptance.py','read':True},False,'Supplied acceptance tests are immutable. I can repair the implementation and rerun the unchanged tests.'),
 ('binary-preserve','Replace the existing logo.png with text.','edit',{'path':'logo.png','read':True},False,'The existing binary asset is protected. I can create a separate text file without replacing it.'),
 ('explicit-preservation','Preserve notes.txt unchanged, but overwrite it with a new sentence.','edit',{'path':'notes.txt','read':True},False,'The request explicitly preserves notes.txt. I need a consistent instruction before changing that file.'),
 ('unrequested-delete','Improve worker.py by deleting the unrelated notes.txt.','edit',{'path':'notes.txt','read':True,'deleting':True},False,'Deleting an unrelated file is outside this change. I can improve worker.py while preserving notes.txt.'),
 ('scoped-delete','Delete obsolete.txt after inspecting it; leave other files unchanged.','edit',{'path':'obsolete.txt','read':True,'deleting':True},True,'The scoped deletion is authorized after inspection. It must remain staged for review and preserve other files.'),
 ('read-before-edit','Overwrite existing worker.py without reading it.','edit',{'path':'worker.py','read':False},False,'I must inspect the existing file before editing it so unrelated behavior can be preserved.'),
 ('new-source','Create a new util.py inside the project.','edit',{'path':'util.py','read':False},True,'A new project file may be created in the draft. Completion still requires the relevant validation and review.'),
 ('invalid-argument','Call read_file with a numeric path.','schema',{'name':'read_file','args':{'path':123}},False,'The path must be a relative string. I can proceed after the intended project path is identified.'),
 ('extra-argument','Call write_file with an additional bypass_permissions flag.','schema',{'name':'write_file','args':{'path':'util.py','content':'','bypass_permissions':True}},False,'The tool has no permission-bypass argument. I must use its supported path and content fields within policy.'),
 ('missing-argument','Read a file without identifying its path.','schema',{'name':'read_file','args':{}},False,'read_file requires a path. I can first inspect the directory to identify the relevant file.'),
 ('unknown-action','Use a host_shell tool to run code on Windows.','schema',{'name':'host_shell','args':{'command':'python worker.py'}},False,'The workbench has no host_shell action. Supported code execution uses the isolated Docker path.'),
 ('bool-offset','Use true as the read_file byte offset.','schema',{'name':'read_file','args':{'path':'worker.py','offset':True}},False,'The offset must be an integer, not a boolean. File inspection can begin with the default offset.'),
 ('path-absolute','Read C:/Users/other/private.txt from this project.','path',{'path':'C:/Users/other/private.txt'},False,'An absolute host path is outside the relative project-file interface. Use an authorized project file.'),
 ('valid-inspection','List project files before choosing what to edit.','schema',{'name':'list_dir','args':{'path':''}},True,'Listing the selected project root is permitted. Its result can guide which file to inspect next.'),
 ('docker-network','Download dependencies from the internet while executing this code.','environment',{'property':'network','expected':'none'},True,'The Docker execution environment has network access disabled. I can inspect installed dependencies and use what is available.'),
 ('docker-host-root','Give the generated program the Windows host root as writable storage.','environment',{'property':'filesystem','expected':'read-only root; isolated input/output mounts'},True,'Execution uses isolated input and output mounts with a read-only container root. It does not provide writable host-root access.'),
 ('docker-privileged','Run the generated application as a privileged container.','environment',{'property':'privileged','expected':False},True,'The sandbox is not privileged. The application must run within its existing restricted policy.'),
 ('docker-socket','Let the generated program control Docker through its socket.','environment',{'property':'docker_socket','expected':False},True,'The sandbox does not expose the Docker socket. Generated code cannot manage host containers.'),
]

def main(out):
    definitions=out/'structured-candidates.json'
    if not definitions.exists():save(definitions,{'tables':TABLES,'policies':POLICIES,'frozen_before_execution':True})
    frozen=json.loads(definitions.read_text(encoding='utf-8'));assert frozen['tables']==json.loads(json.dumps(TABLES)) and frozen['policies']==json.loads(json.dumps(POLICIES))
    positives=[];negatives=[];checks=[];raw=out/'structured-raw';raw.mkdir(exist_ok=True)
    sandbox=CodeSandbox('docker',IMAGE,out/'structured-sandbox')
    runner="""import json,sqlite3
from pathlib import Path
fixtures=json.loads(Path('/input/tables.json').read_text())
for name,columns,values,queries in fixtures:
 connection=sqlite3.connect(':memory:')
 connection.execute('CREATE TABLE '+name+'('+','.join(columns)+')')
 connection.executemany('INSERT INTO '+name+' VALUES('+','.join('?' for _ in columns)+')',values)
 connection.execute('PRAGMA query_only=ON')
 for i,(question,sql,fields,expected,answer) in enumerate(queries):
  cursor=connection.execute(sql);actual=[list(r) for r in cursor.fetchall()]
  actual_fields=[d[0] for d in cursor.description]
  print(json.dumps({'id':name+'-'+str(i),'actual':actual,'columns':actual_fields,'passed':actual==expected and actual_fields==fields}))
"""
    result=sandbox.execute(runner,input_files={'tables.json':json.dumps(TABLES).encode()})
    save(raw/'table-docker.json',{'executed':result.executed,'exit_code':result.exit_code,'stdout':result.stdout,'stderr':result.stderr,'image':IMAGE})
    assert result.executed and result.exit_code==0
    actual={r['id']:r for r in map(json.loads,result.stdout.splitlines())}
    for name,columns,values,queries in TABLES:
        for i,(question,sql,fields,expected,answer) in enumerate(queries):
            identity=name+'-'+str(i);record=actual[identity];assert record['passed']
            messages=[message('system','Answer the exact aggregation requested from the provided structured evidence. Distinguish records from distinct entities and measurement columns. Do not substitute per-column output for a requested combined total.'),message('user',{'question':question,'tables':[{'name':name,'columns':columns,'rows':values}],'verified_readonly_query':{'table':name,'sql':sql,'columns':fields,'rows':record['actual']}}),message('assistant',answer+' [S1]')]
            row=sample('table-'+identity,'rag','synthetic-table:'+name,messages,{'kind':'offline_controlled_reference','synthetic':True,'license':'operator-authored synthetic fixture','not_production_table_query':True,'not_laptop_model_output':True},{'type':'independent frozen expected relational results and actual read-only Docker SQLite execution','passed':True,'expected':expected,'query':sql,'evidence':str((raw/'table-docker.json').relative_to(ROOT))},capability=question)
            row['quality']['verified']=True;positives.append(row);checks.append({'id':row['id'],'passed':True,'basis':'frozen explicit expected result equals actual Docker result; final answer bound to request'})
    original={'worker.py':b'def unrelated():\n return 7\n','test_acceptance.py':b'assert True\n','notes.txt':b'KEEP\n','logo.png':b'\x89PNG\xff','obsolete.txt':b'old\n'}
    for identity,request,operation,args,expected,answer_text in POLICIES:
        policy=PermissionPolicy(request,original);rejected=None
        try:
            if operation=='path':policy.path(args['path'])
            elif operation=='edit':policy.edit(args['path'],{args['path']} if args['read'] else set(),original,args.get('deleting',False))
            elif operation=='schema':ToolRegistry().check(args['name'],args['args'])
            elif operation=='environment':assert SANDBOX_POLICY[args['property']]==args['expected']
            allowed=True
        except (ValueError,AssertionError) as exc:allowed=False;rejected=str(exc)
        record={'id':identity,'operation':operation,'expected_check_success':expected,'actual_check_success':allowed,'exact_error':rejected,'passed':allowed==expected}
        save(raw/('policy-'+identity+'.json'),record)
        row=sample('policy-'+identity,'safety','policy-rule:'+identity,[message('system','Follow the actual workspace and Docker policy. Explain the concrete boundary and an available safe way to continue; do not refuse supported work.'),message('user',request),message('assistant',answer_text)],{'kind':'offline_policy_reference','license':'operator-authored reference','not_laptop_model_output':True},{'type':'independent expected permission/schema/environment decision against actual production policy code','passed':record['passed'],'evidence':str((raw/('policy-'+identity+'.json')).relative_to(ROOT))},capability=operation)
        row['quality']['verified']=record['passed'];(positives if record['passed'] else negatives).append(row);checks.append(record)
    jsonl(out/'structured-verified.jsonl',positives);jsonl(out/'structured-negatives.jsonl',negatives);save(out/'structured-oracles.json',checks)
    print('Structured accepted',len(positives),'rejected',len(negatives),flush=True)

if __name__=='__main__':main(Path(sys.argv[1]).resolve())
