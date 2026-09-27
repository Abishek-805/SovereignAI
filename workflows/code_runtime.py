"""Fixed entry-point commands, always executed by the Docker sandbox."""
import json
from pathlib import PurePosixPath

from backend.contracts import WorkbenchError

LANGUAGES = {'.py':'Python', '.js':'JavaScript', '.mjs':'JavaScript', '.cjs':'JavaScript',
             '.ts':'TypeScript', '.java':'Java', '.c':'C', '.cpp':'C++', '.cc':'C++',
             '.go':'Go', '.rs':'Rust', '.php':'PHP', '.rb':'Ruby', '.sh':'Shell',
             '.sql':'SQL', '.html':'HTML', '.css':'CSS', '.json':'JSON', '.md':'Markdown', '.txt':'Text'}


def runner(target, mode='check', tests=False):
    suffix = PurePosixPath(target).suffix.lower()
    if suffix not in LANGUAGES or mode not in {'check','run'}:
        raise WorkbenchError('unsupported_language', 'This file can be edited, but no local execution adapter is configured for it.')
    # Input paths are validated by CodingWorkspace and CodeSandbox before this script runs.
    return '''import os, sys, subprocess, shutil, json
from pathlib import Path
target, suffix, mode, tests = json.loads(''' + repr(json.dumps([target,suffix,mode,tests])) + ''')
root = Path('/output/project')
shutil.copytree('/input', root, ignore=shutil.ignore_patterns('program.py'))
os.chdir(root)
os.environ.update(HOME='/output', TMPDIR='/output', GOCACHE='/output/go-cache', GOTOOLCHAIN='local', GOPROXY='off', GOSUMDB='off')
def command(args):
    completed = subprocess.run(args, timeout=110 if run else 25)
    if completed.returncode: sys.exit(completed.returncode)
run = mode == 'run'
if suffix == '.py':
    if tests:
        sys.path.insert(0,str(root))
        import unittest
        suite = unittest.defaultTestLoader.discover(str(root), pattern='test_*.py')
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        sys.exit(0 if result.testsRun and result.wasSuccessful() else 1)
    if run: command(['python', target])
    else: compile(Path(target).read_text(), target, 'exec')
elif suffix in ('.js','.mjs','.cjs'):
    command(['node', target] if run else ['node','--check',target])
elif suffix == '.ts':
    command(['tsc',target,'--target','es2020','--module','commonjs','--skipLibCheck','--outDir','/output/ts-build'])
    if run: command(['node', '/output/ts-build/'+Path(target).stem+'.js'])
elif suffix == '.java':
    Path('/output/classes').mkdir()
    command(['javac','-J-Xmx128m','-d','/output/classes',target])
    if run: command(['java','-Xmx128m','-XX:ReservedCodeCacheSize=32m','-XX:CompressedClassSpaceSize=32m','-cp','/output/classes',Path(target).stem])
elif suffix in ('.c','.cpp','.cc'):
    compiler = 'gcc' if suffix == '.c' else 'g++'
    command([compiler,target,'-o','/output/app'] if run else [compiler,'-fsyntax-only',target])
    if run: command(['/output/app'])
elif suffix == '.go':
    os.environ['GOCACHE']='/opt/go-cache'
    command(['go','build','-o','/output/app',target])
    if run: command(['/output/app'])
elif suffix == '.rs':
    command(['rustc',target,'-o','/output/app'])
    if run: command(['/output/app'])
elif suffix == '.php': command(['php',target] if run else ['php','-l',target])
elif suffix == '.rb': command(['ruby',target] if run else ['ruby','-c',target])
elif suffix == '.sh': command(['bash',target] if run else ['bash','-n',target])
elif suffix == '.sql':
    import sqlite3
    db = sqlite3.connect(':memory:')
    db.executescript(Path(target).read_text())
elif suffix == '.json': json.loads(Path(target).read_text())
else: Path(target).read_text(encoding='utf-8')
print('Execution finished.' if run else 'Check passed. This does not prove functional correctness.')
'''
