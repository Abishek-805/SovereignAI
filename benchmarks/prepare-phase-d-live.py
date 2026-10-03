"""Prepare the separate integration trace, not part of primary pass counts."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
s=(root/'benchmarks/evaluate-phase-d.py').read_text(encoding='utf-8')
s=s.replace('benchmarks/phase-d-handoff','benchmarks/phase-d-live-integration').replace('benchmarks/phase-d-tasks.py','benchmarks/phase-d-live-task.py').replace('Phase D Grounded Handoff','Phase D Parcel Manifest Live Integration')
s=s.replace("order=['A','B','C'];order=order[i%3:]+order[:i%3]","order=['C']").replace("'executions':len(cases)*3","'executions':len(cases)")
(root/'benchmarks/evaluate-phase-d-live.py').write_text(s,encoding='utf-8')
