"""Create isolated Phase D harness from the preserved Phase C scaffolding."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
s=(root/'benchmarks/evaluate-code-fidelity.py').read_text()
s=s.replace('Phase C — Code Fidelity & Repair','Phase D — Grounded Handoff and Repair').replace('benchmarks/code-fidelity-repair','benchmarks/phase-d-handoff').replace('benchmarks/code-fidelity-tasks.py','benchmarks/phase-d-tasks.py').replace('Code Fidelity & Repair','Phase D Grounded Handoff')
s=s.replace('reference.files(case)',"case['private_reference']").replace("if arm in {'A','B'} else decision","if arm in {'A','B','C'} else decision")
s=s.replace("reference=load('fidelity_reference','benchmarks/code-fidelity-reference.py')","contract_module=load('phase_d_contract','benchmarks/phase-d-contract.py')")
s=s.replace("traces={'model_requests'", "public_contract=contract_module.contract(case)\n traces={'public_contract':public_contract,'model_requests'")
s=s.replace("entry={'arguments':a,'options':kw}","if arm=='C':a=(a[0],[{'public_source_contract':public_contract}])\n  entry={'arguments':a,'options':kw}")
s=s.replace("entry={'repair_history':kw.get('history',[])","if arm=='C':\n   public_contract['workspace']=a[0];contract_module.validate(public_contract,case)\n   kw['history']=[*(kw.get('history') or []),'assistant: Public handoff contract (original request remains authoritative): '+json.dumps(public_contract)]\n  entry={'repair_history':kw.get('history',[])")
s=s.replace("'policy':'A force Coder; B force existing Qwen plan then Coder; C untouched current Smart Router. Same current tools and 3-attempt runner, private Docker oracles, isolated data, no outcome learning. Rotating task-level order; residency carryover captured, not cold equalized.'", "'policy':'Phase D: A Coder direct, B existing Qwen plan then Coder, C same Qwen/Coder with grounded structured handoff. Common preservation validation, unchanged repair budget/feedback. Isolated instance overrides only, router production frozen.'")
(root/'benchmarks/evaluate-phase-d.py').write_text(s,encoding='utf-8')
