"""Check the adjusted package and observed unexecuted Colab cells."""
import ast, hashlib, json, sys, zipfile
from pathlib import Path

def main(p):
    read=lambda n:json.loads((p/n).read_text(encoding='utf-8'))
    digest=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
    codes=read('colab-cell-sources.json');ui=read('colab-ui-cells-observed.json')
    assert len(ui)==len(codes)==6
    assert all(ast.dump(ast.parse(x['text'].replace('\u00a0',' ')))==ast.dump(ast.parse(codes[i])) for i,x in enumerate(ui))
    manifest=read('release-manifest-adjusted.json')
    assert all(digest(p/n)==d for n,d in manifest['artifact_sha256'].items())
    assert all(digest(Path(manifest['canonical_namespace'])/n)==d for n,d in manifest['canonical_artifact_hashes'].items())
    with zipfile.ZipFile(p/'sovereignai-adjusted-release-colab.zip') as z:
        assert z.testzip() is None
        package=json.loads(z.read('colab-package-manifest.json'))
        assert all(hashlib.sha256(z.read(n)).hexdigest()==d for n,d in package['files'].items())
        helper={};exec(compile(z.read('colab_format_helpers.py'),'colab_format_helpers.py','exec'),helper)
        assert helper['scan']('73+19; answer=92') and not helper['scan']('What is 73 + 19?')
    snap=(p/'colab-final-dom.txt').read_text(encoding='utf-8')
    assert snap.count('generic: "[ ]"')==6 and 'All changes saved' in snap
    result={'status':'PASS','all_six_colab_cells_ast_match_local_notebook':True,'six_new_cells_unexecuted':True,'colab_saved':True,'canonical_hashes_unchanged':True,'release_artifact_hashes_verified':True,'zip_members_verified':True,'portable_scanner_controls_passed':True,'base_model_loaded':False,'training_started':False,'production_changed':False}
    (p/'completion-self-check.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (p/'completion-manifest.json').write_text(json.dumps({'status':'FORMAT_GATE_RECOVERED','artifacts_sha256':{f.name:digest(f) for f in p.iterdir() if f.is_file() and f.name!='completion-manifest.json'}},indent=2),encoding='utf-8')
    print(json.dumps(result))

if __name__=='__main__':main(Path(sys.argv[1]).resolve())
