"""Isolated single-worker kernel. No publication or production integration."""
from dataclasses import asdict, dataclass
import difflib
import hashlib
import json
import math
from pathlib import PurePosixPath
import time

from router.sandbox import safe_relative_name, sensitive_project_path


@dataclass(frozen=True)
class TaskBudget:
    max_model_calls: int = 20
    max_tool_calls: int = 40
    max_repair_attempts: int = 5
    max_sandbox_runs: int = 12
    timeout_seconds: float = 300
    max_output_tokens: int = 12000

    def __post_init__(self):
        for key, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError('Invalid task budget: ' + key)
            if key != 'timeout_seconds' and not isinstance(value, int):
                raise ValueError('Counters must be integers')


def project_map(files):
    """Facts and proposed commands with file evidence; no invented confidence."""
    names = sorted(files)
    languages = sorted({{'.py':'Python', '.js':'JavaScript', '.ts':'TypeScript',
                        '.java':'Java'}.get(PurePosixPath(name).suffix, '') for name in names} - {''})
    commands = []
    for name in names:
        if name in ('main.py', 'app.py'):
            commands.append({'kind':'run', 'command':'python ' + name, 'evidence':name,
                             'basis':'conventional candidate; not a documented entry point'})
    if any(PurePosixPath(name).name.startswith('test_') and name.endswith('.py') for name in names):
        commands.append({'kind':'test', 'command':'python -m unittest discover',
                         'evidence':[name for name in names if PurePosixPath(name).name.startswith('test_')],
                         'basis':'test filenames'})
    if 'package.json' in files:
        try:
            package = json.loads(files['package.json'])
            scripts = package.get('scripts', {})
            if isinstance(scripts, dict):
                commands.extend({'kind':key, 'command':'npm run ' + key,
                                 'script':value, 'evidence':'package.json'}
                                for key,value in scripts.items() if isinstance(value,str))
        except (ValueError, TypeError):
            pass
    configurations = [name for name in names if PurePosixPath(name).name in
                      {'package.json','pyproject.toml','requirements.txt','Dockerfile','Makefile'}]
    return {'languages':languages, 'files':names, 'configurations':configurations,
            'commands':commands, 'framework':'unknown', 'package_manager':
            'npm' if 'package.json' in files else 'pip' if 'requirements.txt' in files else 'unknown'}


def safe_files(files):
    if not isinstance(files, dict) or any(not safe_relative_name(name) or sensitive_project_path(name)
                                         or not isinstance(content,str) for name,content in files.items()):
        raise ValueError('Snapshot contains unsafe paths or non-text content')
    return dict(files)


class MinimalKernel:
    """One task, worker and outer budget. Tools are injected trusted adapters.

    Model callback receives (model, context, token_limit, remaining_seconds) and
    returns (action_dict, consumed_output_tokens). Docker callback receives
    (command, files, remaining_seconds); validator receives (files, seconds).
    Neither callback receives another task's conversation.
    """
    def __init__(self, task, files, model_call, execute, validate, budget=None):
        self.task = task
        self.initial = safe_files(files)
        self.files = dict(self.initial)
        self.model_call, self.execute, self.validate = model_call, execute, validate
        self.budget = budget or TaskBudget()
        self.events = []
        self.counts = dict(model_calls=0,tool_calls=0,repair_attempts=0,sandbox_runs=0,output_tokens=0)

    def diff(self):
        changed = [name for name in sorted(set(self.initial)|set(self.files))
                   if self.initial.get(name) != self.files.get(name)]
        diff = ''.join(''.join(difflib.unified_diff(self.initial.get(name,'').splitlines(True),
                    self.files.get(name,'').splitlines(True), fromfile='before/'+name,tofile='after/'+name))
                    for name in changed)
        return changed, diff

    def observation(self, result):
        if not isinstance(result,dict) or result.get('docker_executed') is not True:
            raise RuntimeError('Docker execution was not confirmed')
        if type(result.get('exit_code')) is not int:
            raise RuntimeError('Missing actual exit code')
        if any(not isinstance(result.get(name),str) for name in ('stdout','stderr')):
            raise RuntimeError('Missing actual output')
        return {**result, 'stdout':result['stdout'][-16000:], 'stderr':result['stderr'][-16000:]}

    def run(self):
        started = time.monotonic()
        latest = {}
        failed = False
        def remaining():
            return self.budget.timeout_seconds - (time.monotonic()-started)
        def result(state, reason):
            return {'state':state,'reason':reason,'task_id':self.task.task_id,
                    'model':self.task.model,'counts':dict(self.counts),'events':self.events,
                    'files':dict(self.files),'elapsed_seconds':time.monotonic()-started}
        while remaining() > 0:
            if self.counts['model_calls'] >= self.budget.max_model_calls or self.counts['output_tokens'] >= self.budget.max_output_tokens:
                return result('BUDGET_EXHAUSTED','model budget')
            changed, diff = self.diff()
            context = json.loads(self.task.context(workspace_id=self.task.workspace_id,
                       workspace_revision=self.task.workspace_revision,
                       current_state=json.dumps({'changed_files':changed}),current_diff=diff))
            context.update(project=project_map(self.files), latest_observation=latest,
                           trajectory=self.events, budget_remaining_seconds=remaining())
            self.counts['model_calls'] += 1
            try:
                action, tokens = self.model_call(self.task.model,context,
                    min(2048,self.budget.max_output_tokens-self.counts['output_tokens']),remaining())
                if type(tokens) is not int or tokens < 0:
                    raise ValueError('Invalid token accounting')
                self.counts['output_tokens'] += tokens
                if self.counts['output_tokens'] > self.budget.max_output_tokens:
                    return result('BUDGET_EXHAUSTED','output token budget')
                if remaining() <= 0:
                    return result('BUDGET_EXHAUSTED','deadline')
                if not isinstance(action,dict):
                    raise ValueError('Action must be structured JSON')
                kind = action.get('action')
                shapes = {'read_file':{'action','path'},'apply_patch':{'action','patch'},
                          'exec':{'action','command'},'finish':{'action','reason'}}
                if kind not in shapes or set(action) != shapes[kind]:
                    raise ValueError('Invalid action schema')
                if self.counts['tool_calls'] >= self.budget.max_tool_calls:
                    return result('BUDGET_EXHAUSTED','tool budget')
                self.counts['tool_calls'] += 1
                if kind == 'read_file':
                    if action['path'] not in self.files:
                        raise ValueError('File is absent from task snapshot')
                    content = self.files[action['path']]
                    latest = {'path':action['path'],'content':content,
                              'sha256':hashlib.sha256(content.encode()).hexdigest()}
                elif kind == 'apply_patch':
                    # Patch is JSON text: [{path, before_sha256, content}]. Null
                    # content deletes a named file; null digest creates a new one.
                    if failed:
                        if self.counts['repair_attempts'] >= self.budget.max_repair_attempts:
                            return result('BUDGET_EXHAUSTED','repair budget')
                        self.counts['repair_attempts'] += 1
                    changes = json.loads(action['patch'])
                    if not isinstance(changes,list) or not changes:
                        raise ValueError('Patch requires changes')
                    candidate = dict(self.files)
                    for change in changes:
                        if not isinstance(change,dict) or set(change) != {'path','before_sha256','content'}:
                            raise ValueError('Invalid patch schema')
                        name = change['path']
                        if not safe_relative_name(name) or sensitive_project_path(name):
                            raise ValueError('Unsafe patch path')
                        old = candidate.get(name)
                        digest = hashlib.sha256(old.encode()).hexdigest() if old is not None else None
                        if change['before_sha256'] != digest:
                            raise ValueError('Patch base mismatch')
                        if change['content'] is None:
                            if old is None: raise ValueError('Cannot delete absent file')
                            del candidate[name]
                        elif isinstance(change['content'],str):
                            candidate[name] = change['content']
                        else: raise ValueError('Patch content must be text or null')
                    self.files = safe_files(candidate)
                    latest = {'changed_files':self.diff()[0]}
                else:
                    if self.counts['sandbox_runs'] >= self.budget.max_sandbox_runs:
                        return result('BUDGET_EXHAUSTED','sandbox budget')
                    self.counts['sandbox_runs'] += 1
                    if kind == 'exec':
                        if not isinstance(action['command'],str) or not action['command'].strip():
                            raise ValueError('Command must be text')
                        latest = self.observation(self.execute(action['command'],dict(self.files),remaining()))
                    else:
                        latest = self.observation(self.validate(dict(self.files),remaining()))
                    failed = latest['exit_code'] != 0
                    self.events.append({'action':action,'observation':latest})
                    if remaining() <= 0:
                        return result('BUDGET_EXHAUSTED','deadline')
                    if kind == 'finish' and not failed:
                        return result('READY_FOR_REVIEW','validation passed')
                    continue
                self.events.append({'action':action,'observation':latest})
            except (ValueError, KeyError, TypeError) as error:
                latest = {'tool_error':str(error)}
                self.events.append({'observation':latest})
            except Exception as error:
                return result('BLOCKED',type(error).__name__+': '+str(error))
        return result('BUDGET_EXHAUSTED','deadline')
