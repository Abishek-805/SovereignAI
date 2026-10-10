"""Append-only expansion registration and permitted public source acquisition."""
import hashlib, json, urllib.request, zipfile, io
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / 'sovereignai-finetuning'
PIN = 'a1e7371c5e006f4e8b314bd23d99220d2fe44c51'
IMAGE = 'sha256:6f6ac11cda347a185454338dee35d77003e066579a3261b52b7c6ff1048c8573'

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)
def rows(path): return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]
def jsonl(path, values):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(''.join(json.dumps(v, ensure_ascii=False)+'\n' for v in values), encoding='utf-8')
    temporary.replace(path)
def fetch(path, url):
    if path.exists(): return
    with urllib.request.urlopen(url, timeout=120) as response: data = response.read()
    path.write_bytes(data)

def main():
    out = ROOT / 'evidence/dataset-expansion' / datetime.now().strftime('%Y%m%d-%H%M%S')
    out.mkdir(parents=True)
    snapshot = out / 'immutable-seed'; snapshot.mkdir()
    for name in ('positive-trajectories.jsonl','negative-trajectories.jsonl','train.jsonl','validation.jsonl','internal-test.jsonl'):
        (snapshot/name).write_bytes((SEED/name).read_bytes())
    assert len(rows(snapshot/'positive-trajectories.jsonl')) == 21
    assert len(rows(snapshot/'negative-trajectories.jsonl')) == 14
    protected = {}
    for folder in ('backend','router','rag','workflows','scripts','models','evidence/json-action-adapter-v2','evidence/code-agent-fidelity-v1','sovereignai-finetuning'):
        for file in (ROOT/folder).rglob('*'):
            if file.is_file() and '__pycache__' not in str(file): protected[str(file.relative_to(ROOT))] = digest(file)
    save(out/'manifest.json', {'protected_sha256':protected,'seed_sha256':{p.name:digest(p) for p in snapshot.iterdir()},'training_started':False})
    (out/'PREREGISTRATION.md').write_text('''# Dataset expansion registration
Target approximately 1000 accepted examples, seven categories, 80/10/10 family splits. Existing 21 positives and 14 original quarantines remain byte-identical; expanded collections append new records. No weights, production behavior, historical evidence, held-out tasks/results or training changed. True Base baseline and Colab training remain separate later gates.
Permitted public reference data is distinct from local model generation. Public answers are not claims of laptop model competence. MBPP references must execute in the existing pinned Docker sandbox, pass immutable public assertions and a deliberately broken negative control. Native tool trajectories use real ToolRegistry/ToolExecutor/AgentLoop calls and actual observations, with an explicitly named offline public-reference teacher. No fabricated tools, observations, HTTP responses, model calls, or repair outcomes. Reference teacher selects only preregistered actions; errors reject rather than silently fix source. Public tests prove their supplied scope, not exhaustive correctness.
SQuAD human question/answer annotations are external semantic reference contracts; answer-span/citation checks are integrity checks, not an automated entailment claim. Public-reference candidates require a separate semantic review for release. Extractive summaries preserve exact source sentences; do not claim unrestricted abstractive summarization. OpenBookQA public labels are externally authored quality contracts. GSM8K public worked arithmetic must match actual deterministic calculation; never count calculator results as model reasoning. Synthetic structured tables use a separately executed relational oracle and explicit across-column versus record semantics. Private workbooks are excluded.
Freeze candidate requests, initial files, tool sequences, expected policy decisions and oracles before execution. Reject superficial variants, exact/normalized duplicates and strong near duplicates; related algorithms/repositories/source articles share families even across categories. Only the existing approved post-generation rejection scanner may inspect held-out request signatures; never load solutions/results. Raw failed candidates retained. No oracle weakening, hidden source fixes, truncation, or retry padding. Record sequence length, evidence hashes, coverage, source/license, failure taxonomy and progress after every batch. Fail closed on missing Docker, corruption, preservation breach or source/license uncertainty. The release gate remains DATASET_NEEDS_MORE_VERIFIED_DATA unless all volume, diversity, semantic grounding, safety, format and split gates pass.
''', encoding='utf-8')
    sources = out/'sources'; sources.mkdir()
    urls = {
        'mbpp.jsonl':f'https://raw.githubusercontent.com/google-research/google-research/{PIN}/mbpp/mbpp.jsonl',
        'mbpp-card.md':'https://huggingface.co/datasets/google-research-datasets/mbpp/raw/main/README.md',
        'squad.json':'https://rajpurkar.github.io/SQuAD-explorer/dataset/train-v2.0.json',
        'squad-license.txt':'https://raw.githubusercontent.com/rajpurkar/SQuAD-explorer/master/LICENSE',
        'openbook.zip':'https://ai2-public-datasets.s3.amazonaws.com/open-book-qa/OpenBookQA-V1-Sep2018.zip',
        'openbook-card.md':'https://huggingface.co/datasets/allenai/openbookqa/raw/main/README.md',
        'gsm8k.jsonl':'https://raw.githubusercontent.com/openai/grade-school-math/master/grade_school_math/data/train.jsonl',
        'gsm8k-license.txt':'https://raw.githubusercontent.com/openai/grade-school-math/master/LICENSE',
    }
    inventory=[]
    for name,url in urls.items():
        try:
            fetch(sources/name,url)
            inventory.append({'name':name,'url':url,'sha256':digest(sources/name),'bytes':(sources/name).stat().st_size})
            save(out/'source-acquisition.json',inventory)
        except Exception as exc:
            save(out/'source-acquisition-error.json',{'name':name,'url':url,'error':str(exc)})
            raise
    with zipfile.ZipFile(sources/'openbook.zip') as archive:
        name=next(n for n in archive.namelist() if n.endswith('/Additional/train_complete.jsonl'))
        (sources/'openbook.jsonl').write_bytes(archive.read(name))
    save(out/'source-licenses.json', {'mbpp':{'license':'CC-BY-4.0','authors':'Austin et al., Google Research, 2021','revision':PIN,'conversion':'unchanged reference implementation; new workspace wrapper and independently executed public tests'},'squad':{'license':'CC-BY-SA-4.0','authors':'Rajpurkar et al., Stanford','conversion':'human-annotated extractive QA and clearly labeled extractive summaries; attribution retained'},'openbook':{'license':'Apache-2.0','authors':'Mihaylov, Clark, Khot and Sabharwal, Allen AI, 2018','conversion':'human multiple-choice labels, no fabricated reasoning'},'gsm8k':{'license':'MIT','authors':'Cobbe et al., OpenAI, 2021','conversion':'public worked calculator steps; independently evaluated before accepting'}})
    print(out, flush=True)

if __name__=='__main__': main()
