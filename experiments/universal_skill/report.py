"""Read-only evidence report for the skill experiment."""
from pathlib import Path
import json,statistics
ROOT=Path(__file__).resolve().parents[2]
RUNS=['1791511059906103400','1791511219727358300']

def main():
    evidence=ROOT/'evidence/universal-skill';runs=[]
    for run in RUNS:
        directory=evidence/run;results=json.loads((directory/'results.json').read_text())
        assert len(results)==10 and len({(r['case'],r['arm']) for r in results})==10
        calls=[json.loads(line) for line in (directory/'calls.jsonl').read_text().splitlines()]
        assert all(c['profile_verified'] for c in calls)
        assert all(any('EXPERIMENTAL TASK SKILL' in m.get('content','') for m in c['payload']['messages'])==(c['arm']=='skill') for c in calls)
        integrity=json.loads((directory/'integrity.json').read_text());assert integrity['production_source_unchanged']
        summary={arm:{'stage_checks_passed':sum(r['status'] in {'answered','PASS','PLAN_VALIDATED'} for r in results if r['arm']==arm),
            'median_seconds':statistics.median(r['seconds'] for r in results if r['arm']==arm),
            'model_calls':sum(r['model_calls'] for r in results if r['arm']==arm)} for arm in ('baseline','skill')}
        runs.append({'run_id':run,'summary':summary,'results':results,'integrity':integrity,'actual_calls':len(calls)})
    report={'status':'EXPERIMENT_COMPLETE_PARTIAL_BENEFIT','production_integrated':False,'runs':runs,
        'independent_review':{'museum_overview':'PASS: identity, location, preserved objects and three features match authored evidence; no invented hours',
            'kpr_overview':'FAIL: claim assessor rewrites a conjunct into a span not present in draft; full claim coverage false',
            'table_applicability':'PASS in both arms; reported misrouting was NOT reproduced',
            'coding':'Plan preflight only; not generated applications or Docker execution'},
        'limitations':['Screenshot reconstruction, not original live corpus or sessions: 8098 refused connection.',
            'Five stage probes per arm, two development iterations, no statistical generalization claim.',
            'Skill v2 was revised after v1 failures; these are development probes, not frozen held-out results.',
            'No application runtime changes, UI activation, full generated-code execution or training.',
            'Added skill changes input tokens; output caps, temperature, models and validators remain unchanged.']}
    (ROOT/'universal-skill-test-report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
    latest=runs[-1]['results'];table=[]
    for case in dict.fromkeys(r['case'] for r in latest):
        pair={r['arm']:r for r in latest if r['case']==case}
        table.append(f"| {case} | {pair['baseline']['status']} | {pair['skill']['status']} | {pair['baseline']['seconds']:.2f}s / {pair['skill']['seconds']:.2f}s |")
    text='''# Universal task skill — isolated test report

Date: 2026-10-09 (Asia/Calcutta)

Status: **Experiment complete; partial benefit. Not a universal fix.**

The skill is `experiments/universal_skill/SKILL.md`. It contains no institution names, student identifiers, fixture answers, particular application paths or prompt-specific triggers. It covers resource applicability, grounded synthesis, literal claim assessment, workspace inventories and bounded error feedback. It was injected only into experimental model requests, not installed into the application's runtime skill loader. Skill frontmatter validation passes.

## Test method

Five stage probes were paired without/with the skill. Gemma 4 E2B served the RAG stages; Qwen2.5-Coder-3B-Instruct served workspace planning. Every inference checked actual registered runtime identity/profile. Models ran sequentially. Both arms retain the existing prompts, temperature, output caps, ordinary runtime skills, exact claim gate, one allowed answer repair and preflight validators. The sole treatment is appended skill instructions. No retries were added inside either paired arm. Input tokens necessarily increase with the skill.

Port 8098 refused connection. The institution facts were reconstructed from the screenshot, not represented as the original document. An independently authored museum fixture tests transfer. The table probe contains unrelated assessment rows and the relevant institution excerpt. Coding probes include occupied web source paths and an existing unrelated application. No frozen held-out tasks, dataset examples or training artifacts were opened.

Two iterations were preserved separately. Version 1 first showed an overview benefit but failed literal claim extraction and workspace collision checks. Version 2 strengthened generic verbatim-span and occupied-path guidance; it did not resolve those remaining failures. Both versions' exact skill bytes, requests, responses, results and source hashes survive. This is development testing, not an unbiased held-out benchmark.

## Latest paired results

| Probe | Without skill | With skill | Without / with latency |
|---|---|---|---|
'''+ '\n'.join(table)+'''

The museum answer with the skill is a short overview naming the museum, Seabrook, maritime objects/oral histories and its exhibits, workshops and archive. Each fact matches the fixture and has a citation. The existing independent software binding checks also pass. In both iterations, the baseline instead abstained after review.

The KPR draft-to-abstention failure reproduces in both iterations and both arms. The final assessor proposes `It is approved by AICTE` rather than copying the actual conjunct from the draft. Although the source supports the underlying fact, that rewritten text is absent from the draft. The software reports unsupported claim and incomplete coverage. The skill improved quote length in version 2 but did not fix span extraction. This is assessment-format failure, not evidence that the institution document lacked the fact.

The table probe selected operation none with and without the skill. Therefore the screenshots' invented-cohort error was not reproduced here, and no improvement is attributed to the skill on that issue.

Coding requests still propose conflicting operations. Real shared workspace preflight rejects the calculator plans and the baseline notes plan with `Planned new file already exists`. The version-2 notes plan with the skill is rejected earlier with `The plan repeats a workspace path`; this additional format defect is preserved, not counted as an improvement. Neither arm reaches source generation. The extensionless-directory error in the screenshot was not separately reproduced. A valid plan is only a plan: no working application, Docker run or successful deployment is claimed.

## Preservation and recommendation

All tracked experimental source hashes for backend, RAG, router, workflows and live runtime skill files match before/after each run. Earlier dirty working-tree changes predate this experiment. Production was not restarted, edited or activated; user documents were not changed. No new dependency, model, agent or controller was added. No generated code ran on the host or in Docker because generation was not reached.

Keep this skill as an experimental artifact. The measured overview benefit does not justify declaring the remaining failures solved or integrating it as a universal fix. A future authorized repair should address exact draft-span binding and request-bound plan recovery at their shared boundaries, retaining the current safety validators. Do not hide these failures by relaxing the claim gate or silently overwriting existing files.

Raw evidence: `evidence/universal-skill/` under the run IDs recorded in the JSON report. Reproduce tests with `.app-venv/Scripts/python.exe -m experiments.universal_skill.evaluate`; this creates a fresh run rather than overwriting evidence. The report generator reads the two explicitly designated development runs.
'''
    (ROOT/'universal-skill-test-report.md').write_text(text,encoding='utf-8')
    print(json.dumps({r['run_id']:r['summary'] for r in runs},indent=2))

if __name__=='__main__':main()
