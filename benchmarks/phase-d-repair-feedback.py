"""Public-source diagnostic messages. Never reads the private oracle."""
import ast
def feedback(case,previous):
 diagnostics=[]
 for change in previous.get('changes',[]):
  text=change.get('after')
  if not isinstance(text,str):continue
  try:tree=ast.parse(text)
  except SyntaxError as exc:
   diagnostics.append({'requirement_id':'EXECUTABLE_PYTHON','category':'SOURCE_SYNTAX','observed':exc.msg,'expected_behavior':'Provide syntactically valid Python'});continue
  if 'excluding bool' in case['requirements'][0] and any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='isinstance' for n in ast.walk(tree)):
   diagnostics.append({'requirement_id':'STRICT_TYPE_OBLIGATION','category':'PUBLIC_SOURCE_REVIEW','observed':'Candidate uses isinstance; bool is an int subclass. This is a risk, not proof that all branches accept bool.','expected_behavior':case['requirements'][0]})
  if change['path']=='adapter.py':
   fn=case['required_symbols'][case['allowed_change_paths'][0]][0]
   if not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr==fn for n in ast.walk(tree)):
    diagnostics.append({'requirement_id':'ADAPTER_DELEGATION','category':'PUBLIC_SOURCE_REVIEW','observed':'No direct call to required feature function appears in adapter source; indirect delegation is not excluded by this observation.','expected_behavior':case['requirements'][2]})
 diagnostics.append({'requirement_id':'PUBLIC_BEHAVIOR_CONTRACT','category':'VALIDATION_FAILURE','observed':previous.get('stderr','')[:1500],'expected_behavior':case['requirements'][0]})
 return diagnostics
