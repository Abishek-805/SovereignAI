"""Experimental public handoff and preservation checks; no private oracle access."""
import ast,json
FIELDS={'original_user_request','resolved_goal','workspace','target_files','exact_public_interfaces','required_symbols','required_function_signatures','expected_inputs','expected_outputs','exception_obligations','behavioral_requirements','protected_paths','allowed_change_paths','forbidden_change_paths','existing_diagnostics','source_excerpts','acceptance_requirements'}
def interfaces(files):
 result={}
 for path,text in files.items():
  tree=ast.parse(text);entries=[]
  for node in tree.body:
   if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
    entries.append({'symbol':node.name,'signature':ast.unparse(node.args),'returns':ast.unparse(node.returns) if node.returns else None})
  result[path]={'functions':entries,'imports':[ast.unparse(n) for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))]}
 return result
def contract(case,workspace='isolated-selected-workspace'):
 files=case['context']['initial_files'];public=interfaces(files)
 result={'original_user_request':case['request'],'resolved_goal':case['request'],'workspace':workspace,'target_files':case['allowed_change_paths'],
 'exact_public_interfaces':public,'required_symbols':case['required_symbols'],'required_function_signatures':public,
 'expected_inputs':'Use existing function parameters; type/value obligations are verbatim in behavioral_requirements.',
 'expected_outputs':'Return behavior is verbatim in behavioral_requirements; adapter delegation preserves the return value.',
 'exception_obligations':case['requirements'][0],'behavioral_requirements':case['requirements'],
 'protected_paths':sorted(set(files)-set(case['allowed_change_paths'])),'allowed_change_paths':case['allowed_change_paths'],
 'forbidden_change_paths':sorted(set(files)-set(case['allowed_change_paths'])),'existing_diagnostics':[],
 'source_excerpts':{p:t[:3000] for p,t in files.items()},'acceptance_requirements':case['requirements']}
 validate(result,case);return result
def validate(value,case):
 assert set(value)==FIELDS
 assert value['original_user_request']==case['request']
 assert value['allowed_change_paths']==case['allowed_change_paths']
 assert sum(map(len,value['source_excerpts'].values()))<=10000
 assert all(isinstance(v,(str,list,dict)) for v in value.values())
 json.dumps(value)
def preservation(case,files):
 diagnostics=[];original=case['context']['initial_files']
 for path,text in original.items():
  candidate=files.get(path);candidate=candidate.decode() if isinstance(candidate,bytes) else candidate
  if candidate is None:diagnostics.append({'requirement_id':'REQUIRED_FILE','path':path,'category':'PRESERVATION','expected_behavior':'Keep required file'});continue
  if path not in case['allowed_change_paths'] and candidate!=text:diagnostics.append({'requirement_id':'PROTECTED_PATH','path':path,'category':'PRESERVATION','expected_behavior':'Keep protected source byte-identical'})
  try:
   old=ast.parse(text);new=ast.parse(candidate)
  except SyntaxError:continue
  functions={n.name:n for n in new.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
  assignments={t.id:n.value for n in new.body if isinstance(n,ast.Assign) for t in n.targets if isinstance(t,ast.Name)}
  for node in old.body:
   if not isinstance(node,ast.FunctionDef):continue
   args=functions[node.name].args if node.name in functions else assignments[node.name].args if isinstance(assignments.get(node.name),ast.Lambda) else None
   if args is None:diagnostics.append({'requirement_id':'REQUIRED_SYMBOL','path':path,'symbol':node.name,'category':'PRESERVATION','expected_behavior':'Preserve required callable'})
   elif ast.dump(args)!=ast.dump(node.args):diagnostics.append({'requirement_id':'REQUIRED_SIGNATURE','path':path,'symbol':node.name,'category':'PRESERVATION','expected_behavior':'Preserve exact public signature'})
 for path in set(files)-set(original):
  if path not in case['allowed_change_paths']:diagnostics.append({'requirement_id':'TARGET_SCOPE','path':path,'category':'PRESERVATION','expected_behavior':'Change only allowed files'})
 return diagnostics
