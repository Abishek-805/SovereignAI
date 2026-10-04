"""Evidence-based project commands; never guess an arbitrary first source file."""
import ast,json,re,shlex
from pathlib import PurePosixPath
from backend.contracts import WorkbenchError


def inspect_project(files):
    packages=[name for name in files if PurePosixPath(name).name=='package.json']
    if 'package.json' not in files and len(packages)==1:
        prefix=str(PurePosixPath(packages[0]).parent)+'/'
        result=inspect_project({name[len(prefix):]:content for name,content in files.items() if name.startswith(prefix)})
        result['cwd']=prefix.rstrip('/')
        result['evidence']=[prefix+name for name in result['evidence']]
        return result
    names=set(files)
    result={'files':sorted(names),'language':None,'framework':None,'package_manager':None,'commands':{},'evidence':[]}
    if 'package.json' in names:
        package=json.loads(files['package.json'].decode('utf-8'))
        scripts=package.get('scripts',{})
        result.update(language='JavaScript',package_manager='npm',framework='Vite' if 'vite' in package.get('devDependencies',{}) else 'Node.js')
        result['evidence'].append('package.json')
        for kind in ('test','build','start','dev'):
            if isinstance(scripts.get(kind),str):result['commands'][kind]='npm run '+kind+' --offline'
        entry=package.get('main')
        if isinstance(entry,str) and entry in names:result['commands']['run']='node '+shlex.quote(entry)
        elif 'start' in scripts:result['commands']['run']='npm run start --offline'
        elif 'build' in scripts:result['commands']['run']='npm run build --offline'
        return result
    if any(name.endswith('.py') for name in names):
        result['language']='Python';result['package_manager']='pip'
        documented=[]
        for name in names:
            if PurePosixPath(name).name.lower().startswith('readme'):
                text=files[name].decode('utf-8',errors='replace')
                for match in re.finditer(r'\bpython(?:3)?\s+([\w./-]+\.py)\b',text):
                    if match.group(1) in names:documented.append(match.group(1));result['evidence'].append(name)
        entries=list(dict.fromkeys(documented)) or [name for name in ('main.py','app.py','cli.py','__main__.py') if name in names]
        if not entries:
            for name in sorted(names):
                if not name.endswith('.py') or PurePosixPath(name).name.startswith('test_'):continue
                try:tree=ast.parse(files[name].decode('utf-8'))
                except (SyntaxError,UnicodeDecodeError):continue
                if any(isinstance(node,ast.If) and isinstance(node.test,ast.Compare)
                       and isinstance(node.test.left,ast.Name) and node.test.left.id=='__name__'
                       and any(isinstance(value,ast.Constant) and value.value=='__main__' for value in node.test.comparators)
                       for node in tree.body):entries.append(name)
        if len(entries)==1:
            entry=entries[0];parts=PurePosixPath(entry).with_suffix('').parts
            result['commands']['run']='python -m '+'.'.join(parts) if len(parts)>1 and all(part.isidentifier() for part in parts) else 'python '+shlex.quote(entry)
            result['evidence'].append(entry)
        if any(PurePosixPath(name).name.startswith('test_') and name.endswith('.py') for name in names):result['commands']['test']='python -m unittest discover -v'
    elif any(name.endswith('.java') for name in names):
        result['language']='Java'
        entries=[name for name in names if name.endswith('.java') and re.search(rb'public\s+static\s+void\s+main',files[name])]
        if len(entries)==1:
            target=entries[0];package=re.search(rb'(?m)^\s*package\s+([\w.]+)\s*;',files[target])
            classname=(package.group(1).decode()+'.' if package else '')+PurePosixPath(target).stem
            result['commands']['run']='mkdir -p /output/classes && javac -sourcepath '+shlex.quote('.:'+str(PurePosixPath(target).parent))+' -d /output/classes '+shlex.quote(target)+' && java -cp /output/classes '+shlex.quote(classname)
            result['evidence'].append(target)
    return result
