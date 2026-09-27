from pathlib import Path
import json, hashlib, subprocess, shutil, sys
ROOT = Path(__file__).resolve().parent
MODEL = ROOT / 'models/bge-small-en-v1.5'
MANIFEST = ROOT / 'embedding-manifest.json'
def main():
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8-sig'))
    missing = [item for item in manifest['files'] if not (MODEL/item['path']).is_file() or hashlib.sha256((MODEL/item['path']).read_bytes()).hexdigest() != item['sha256']]
    if missing:
        hf = shutil.which('hf') or str(Path(sys.executable).with_name('hf.exe'))
        if not Path(hf).is_file() and not shutil.which(hf):
            raise SystemExit('Install the Hugging Face CLI (hf) for setup, then rerun. Runtime does not download models.')
        subprocess.run([hf, 'download', manifest['repository'], *[item['path'] for item in missing], '--revision', manifest['revision'], '--local-dir', str(MODEL)], check=True)
    for item in manifest['files']:
        if hashlib.sha256((MODEL/item['path']).read_bytes()).hexdigest() != item['sha256']:
            raise SystemExit('Asset checksum failed: ' + item['path'])
    (MODEL/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('All pinned embedding assets verified. Runtime is local-only.')
if __name__ == '__main__': main()
