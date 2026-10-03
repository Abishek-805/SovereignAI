"""Prepare secondary repair-feedback ablation, separate from primary handoff study."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
s=(root/'benchmarks/evaluate-phase-d.py').read_text(encoding='utf-8')
s=s.replace('benchmarks/phase-d-handoff','benchmarks/phase-d-repair-feedback').replace('Phase D Grounded Handoff','Phase D Public Repair Feedback')
s=s.replace("arm=='C'","arm=='R'").replace("{'A','B','C'}","{'A','B','C','R'}").replace("order=['A','B','C'];order=order[i%3:]+order[:i%3]","order=['R']")
s=s.replace("contract_module=load('phase_d_contract','benchmarks/phase-d-contract.py')","contract_module=load('phase_d_contract','benchmarks/phase-d-contract.py')\nfeedback_module=load('phase_d_feedback','benchmarks/phase-d-repair-feedback.py')")
s=s.replace("public_contract['workspace']=a[0];contract_module.validate(public_contract,case)","public_contract['workspace']=a[0];contract_module.validate(public_contract,case)\n   prior=[at['result'] for at in traces['candidate_attempts'] if 'result' in at]\n   if prior and prior[-1].get('state')!='completed':\n    kw['history']=[*(kw.get('history') or []),'assistant: Bounded public diagnostic (no private tests): '+json.dumps(feedback_module.feedback(case,prior[-1]))]")
s=s.replace('executions\':len(cases)*3','executions\':len(cases)')
s=s.replace("'policy':'Phase D: A Coder direct, B existing Qwen plan then Coder, C same Qwen/Coder with grounded structured handoff. Common preservation validation, unchanged repair budget/feedback. Isolated instance overrides only, router production frozen.'","'policy':'Secondary Phase D R vs primary C: identical grounded handoff with added public-source diagnostic repair feedback only when existing repair runs. Same bounded repair budget, tools, models, sandbox. No extra repair attempts.'")
(root/'benchmarks/evaluate-phase-d-repair.py').write_text(s,encoding='utf-8')
