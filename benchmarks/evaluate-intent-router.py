"""Offline CPU screening; this cannot execute tools or change production policy.

Compare word/character TF-IDF prototypes with the installed CPU BGE encoder.
Similarity and margin are scores, never calibrated confidence probabilities.
The small engineer-authored corpus is a pilot, not independent release evidence.
"""
import hashlib
import json
import platform
import re
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import psutil
import onnxruntime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.settings import Settings
from rag.embedding import Embedder


def terms(text, character=False):
    value = ' '.join(text.lower().split())
    if character:
        value = ' ' + value + ' '
        return [value[i:i+n] for n in (3, 4, 5) for i in range(len(value)-n+1)]
    words = re.findall(r'\w+', value)
    return words + [' '.join(words[i:i+2]) for i in range(len(words)-1)]


class Tfidf:
    def __init__(self, texts, character=False):
        self.character = character
        df = Counter(term for text in texts for term in set(terms(text, character)))
        self.vocab = {term: index for index, term in enumerate(sorted(df))}
        self.idf = np.array([np.log((1+len(texts))/(1+df[term]))+1 for term in sorted(df)], dtype=np.float32)

    def encode(self, texts):
        rows = np.zeros((len(texts), len(self.vocab)), dtype=np.float32)
        for row, text in enumerate(texts):
            for term, count in Counter(terms(text, self.character)).items():
                index = self.vocab.get(term)
                if index is not None:
                    rows[row, index] = (1+np.log(count))*self.idf[index]
        return rows / np.maximum(np.linalg.norm(rows, axis=1, keepdims=True), 1e-12)


def main():
    corpus_path = ROOT/'benchmarks/intent-screening-v1.json'
    raw = corpus_path.read_bytes()
    corpus = json.loads(raw)
    labels, texts = zip(*[(label, text) for label, examples in corpus['development'].items() for text in examples])
    classes = sorted(set(labels))
    process = psutil.Process()
    report = {'dataset_sha256': hashlib.sha256(raw).hexdigest(), 'date': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
              'machine': {'os': platform.platform(), 'cpu': platform.processor(), 'ram_bytes': psutil.virtual_memory().total},
              'runtime': {'python':platform.python_version(), 'numpy':np.__version__, 'onnxruntime':onnxruntime.__version__, 'onnx_threads':2,'provider':'CPUExecutionProvider'},
              'development_count':len(texts), 'held_out_count':len(corpus['held_out']), 'run_count':1,
              'policy': corpus['policy'], 'provenance': corpus['provenance'], 'production_enabled': False, 'methods': {}}
    for method in ['word-tfidf', 'character-tfidf', 'local-bge']:
        started = time.perf_counter()
        rss_before = process.memory_info().rss
        encoder = Embedder(Settings().model_dir) if method=='local-bge' else Tfidf(texts, method=='character-tfidf')
        vectors = encoder.encode(list(texts))
        setup_ms = (time.perf_counter()-started)*1000
        # Maximum similarity per class preserves multiple distinct conversational examples.
        def predict(text):
            start = time.perf_counter()
            similarities = vectors @ encoder.encode([text])[0]
            ranked = sorted([(label, float(max(similarities[i] for i, known in enumerate(labels) if known==label))) for label in classes], key=lambda x:x[1], reverse=True)
            label, score = ranked[0]
            margin = score-ranked[1][1]
            accepted = score>=corpus['policy']['minimum_similarity'] and margin>=corpus['policy']['minimum_margin']
            return {'predicted': label, 'decision': label if accepted else 'defer_to_planner', 'similarity':score,'margin':margin,'elapsed_ms':(time.perf_counter()-start)*1000}
        rows = [{'expected':label,'text':text,**predict(text)} for label,text in corpus['held_out']]
        probes = [{'text':text,**predict(text)} for text in corpus['safety_probes']]
        accepted = [row for row in rows if row['decision']!='defer_to_planner']
        report['methods'][method] = {'setup_ms':setup_ms,'rss_increment_bytes':process.memory_info().rss-rss_before,
            'embedding_revision':encoder.revision if method=='local-bge' else None,
            'accuracy':sum(r['predicted']==r['expected'] for r in rows)/len(rows),
            'coverage':len(accepted)/len(rows),'accepted_correct':sum(r['predicted']==r['expected'] for r in accepted),
            'accepted_count':len(accepted),'unsafe_edit_acceptances':sum(r['decision']=='edit_code' and r['expected']!='edit_code' for r in rows),
            'median_ms':statistics.median(r['elapsed_ms'] for r in rows),'raw_results':rows,'safety_probes':probes}
        print(method, json.dumps({k:v for k,v in report['methods'][method].items() if k not in {'raw_results','safety_probes'}}), flush=True)
    destination=ROOT/'benchmarks/intent-screening-results.json'
    destination.write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
