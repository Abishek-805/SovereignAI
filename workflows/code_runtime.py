"""Fixed entry-point commands, always executed by the Docker sandbox."""
import json
from pathlib import PurePosixPath

from backend.contracts import WorkbenchError

LANGUAGES = {'.py':'Python', '.js':'JavaScript', '.mjs':'JavaScript', '.cjs':'JavaScript',
             '.ts':'TypeScript', '.java':'Java', '.c':'C', '.cpp':'C++', '.cc':'C++',
             '.go':'Go', '.rs':'Rust', '.php':'PHP', '.rb':'Ruby', '.sh':'Shell',
             '.sql':'SQL', '.cs':'C#', '.r':'R', '.lua':'Lua', '.pl':'Perl', '.cxx':'C++', '.bash':'Shell',
             '.html':'HTML', '.htm':'HTML', '.css':'CSS', '.json':'JSON', '.md':'Markdown', '.txt':'Text'}


def runner(target, mode='check', tests=False):
    suffix = PurePosixPath(target).suffix.lower()
    if suffix not in LANGUAGES or mode not in {'check','run'}:
        raise WorkbenchError('unsupported_language', 'This file can be edited, but no local execution adapter is configured for it.')
    if mode == 'run' and suffix in {'.html', '.htm', '.css'}:
        raise WorkbenchError('preview_required', 'HTML uses the Preview button beside Save. CSS is rendered by an HTML page, not run as a standalone program.')
    # Input paths are validated by CodingWorkspace and CodeSandbox before this script runs.
    return '''import os, sys, subprocess, shutil, json
from pathlib import Path
target, suffix, mode, tests = json.loads(''' + repr(json.dumps([target,suffix,mode,tests])) + ''')
root = Path('/output/project')
# Only the sandbox's root wrapper is reserved. A project dependency named
# program.py inside a package is user data and must be copied with its package.
shutil.copytree('/input', root, ignore=lambda source, names: {'program.py'} if Path(source) == Path('/input') else set())
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
elif suffix in ('.c','.cpp','.cc','.cxx'):
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
elif suffix in ('.sh','.bash'): command(['bash',target] if run else ['bash','-n',target])
elif suffix == '.lua': command(['lua5.4',target] if run else ['luac5.4','-p',target])
elif suffix == '.pl': command(['perl',target] if run else ['perl','-c',target])
elif suffix == '.r': command(['Rscript',target] if run else ['Rscript','-e','parse(file=commandArgs(TRUE)[1])',target])
elif suffix == '.cs':
    os.environ.update(DOTNET_CLI_HOME='/output', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1',
                      DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', NUGET_PACKAGES='/output/nuget',
                      DOTNET_GCHeapHardLimit='08000000', DOTNET_gcServer='0', DOTNET_PROCESSOR_COUNT='1')
    project=Path('/output/csharp');project.mkdir()
    shutil.copy2(target,project/'Program.cs')
    # Compile directly against installed framework references: no NuGet restore,
    # MSBuild workers or compiler server, and no package/project claims.
    compiler=next(Path('/usr/lib/dotnet/sdk').glob('*/Roslyn/bincore/csc.dll'))
    references=sorted(Path('/usr/lib/dotnet/packs/Microsoft.NETCore.App.Ref').glob('*/ref/net10.0/*.dll'))
    if not references: raise RuntimeError('Local .NET framework references are missing')
    (project/'GlobalUsings.cs').write_text('global using System; global using System.Collections.Generic; global using System.IO; global using System.Linq; global using System.Threading; global using System.Threading.Tasks;')
    command(['dotnet',str(compiler),'-nologo','-target:exe','-nostdlib+','-out:'+str(project/'App.dll'),
             *['-r:'+str(reference) for reference in references],str(project/'GlobalUsings.cs'),str(project/'Program.cs')])
    (project/'App.runtimeconfig.json').write_text(json.dumps({'runtimeOptions':{'tfm':'net10.0','framework':{'name':'Microsoft.NETCore.App','version':'10.0.0'},'rollForward':'LatestPatch'}}))
    if run: command(['dotnet',str(project/'App.dll')])
elif suffix == '.sql':
    import sqlite3
    db = sqlite3.connect(':memory:')
    db.executescript(Path(target).read_text())
elif suffix == '.json': json.loads(Path(target).read_text())
else: Path(target).read_text(encoding='utf-8')
print('Execution finished.' if run else 'Check passed. This does not prove functional correctness.')
'''
