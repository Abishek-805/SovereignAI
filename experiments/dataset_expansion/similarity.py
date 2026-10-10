"""Flag similar public references for review, without silently deleting valid rows."""
import ast,collections,json,sys
from pathlib import Path
from experiments.dataset_expansion.prepare import rows,save
from experiments.dataset_expansion.release import user_text,shingles,finish_package,ROOT

class Shape(ast.NodeTransformer):
    def visit_Name(self,node):node.id='symbol';return node
    def visit_arg(self,node):node.arg='argument';return node
    def visit_Constant(self,node):node.value=type(node.value).__name__;return node
    def visit_FunctionDef(self,node):self.generic_visit(node);node.name='function';return node

def main(out):
    data=rows(out/'positive-trajectories-expanded.jsonl');requests=[shingles(user_text(r)) for r in data]
    near=[]
    for i,left in enumerate(requests):
        if not left:continue
        for j in range(i):
            right=requests[j];union=left|right;score=len(left&right)/len(union) if union else 0
            if score>=.6:near.append({'left':data[j]['id'],'right':data[i]['id'],'request_5gram_jaccard':score,'same_declared_family':data[j]['family']==data[i]['family']})
    shapes=collections.defaultdict(list)
    for path in (out/'coding-raw').glob('*/definition.json'):
        definition=json.loads(path.read_text(encoding='utf-8'))
        if definition['id'] not in {r['id'] for r in data}:continue
        tree=Shape().visit(ast.parse(definition['public_task']['code']))
        shapes[ast.dump(tree,include_attributes=False)].append(definition['id'])
    report=json.loads((out/'deduplication-report-expanded.json').read_text(encoding='utf-8'))
    split={r['id']:s for s in ('train','validation','internal-test') for r in rows(out/(s+'.jsonl'))}
    cross=[p for p in near if split[p['left']]!=split[p['right']]]
    report.update(near_request_threshold=.6,near_request_pairs=near,near_request_cross_split_pairs=len(cross),near_request_pairs_semantically_reviewed=False,normalized_public_code_shape_groups=[v for v in shapes.values() if len(v)>1],normalization='AST names, parameters and literal values anonymized; operations and control flow retained.',semantic_algorithm_families_audited=False)
    save(out/'deduplication-report-expanded.json',report);save(ROOT/'sovereignai-finetuning-expanded/deduplication-report-expanded.json',report)
    readiness=json.loads((out/'release-readiness.json').read_text(encoding='utf-8'))
    readiness['gates']['near_request_review']=not near
    readiness['failed_gates']=[k for k,v in readiness['gates'].items() if not v]
    expansion=json.loads((out/'dataset-expansion-report.json').read_text(encoding='utf-8'));expansion['readiness']=readiness
    for name,value in [('release-readiness.json',readiness),('dataset-expansion-report.json',expansion)]:
        save(out/name,value);save(ROOT/'sovereignai-finetuning-expanded'/name,value)
    text=(out/'FINAL_REPORT.md').read_text(encoding='utf-8')
    if '\nSimilarity follow-up:' not in text:
        text+=f'\nSimilarity follow-up: {len(near)} request pairs meet the 0.6 five-gram threshold; {len(cross)} cross provisional splits. These are flags, not proven duplicates, and require semantic review before family assignments can be released. No repeated normalized public-code AST shapes were found. Training stays blocked.\n'
        (out/'FINAL_REPORT.md').write_text(text,encoding='utf-8');(ROOT/'sovereignai-finetuning-expanded/FINAL_REPORT.md').write_text(text,encoding='utf-8')
    finish_package(out)
    print(json.dumps({'near_request_pairs':len(near),'repeated_normalized_code_shapes':len(report['normalized_public_code_shape_groups'])}),flush=True)

if __name__=='__main__':main(Path(sys.argv[1]).resolve())
