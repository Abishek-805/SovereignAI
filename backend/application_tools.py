"""Typed application operations: reference access and mutation are separate.

The planner selects only these registered operations. Names resolve uniquely at
execution time; imports never grant the model arbitrary host filesystem access.
"""
from pathlib import Path
import re
from backend.contracts import WorkbenchError
from backend.jobs import Job
from router.tool_registry import ToolRegistry, ToolContract

OPERATIONS = {
    'project_create': 'Create a new managed coding project; target is its name. Subsequent file edits in this plan use the new project.',
    'project_delete': 'Delete the selected managed coding project only when the current request explicitly asks to delete that project.',
    'document_create': 'Create a new text/Markdown document; target is its name, value its text.',
    'document_update': 'Update the text of one existing Knowledge TXT/Markdown document; target is its exact name, value is complete replacement text. Never create it again.',
    'document_import': 'Index a file already in the selected project; target is its relative path.',
    'document_rename': 'Rename one library document; target is current name, value is new name.',
    'document_move': 'Move one library document into a library folder; value is folder.',
    'document_copy': 'Copy one library document into a library folder; value is folder.',
    'document_delete': 'Remove one named document from the library, keeping original source files.',
    'document_duplicates': 'Find exact source-content duplicates in Knowledge; target knowledge, unused fields empty. Does not delete.',
    'document_deduplicate': 'Remove exact source-content duplicate library entries, keeping one per group and all source files; target knowledge, unused fields empty.',
    'file_edit': 'Create or modify requested project code; target is filename, value is the full change instruction.',
    'file_delete': 'Delete one explicitly named project file; target is its relative path.',
    'file_delete_scope': 'Stage deletion of ALL project files and folders, optionally preserving one existing folder and everything inside it. target must be all; value is the preserved folder path or empty.',
    'file_move': 'Move or rename one project file; target is old path, value is new path.',
    'file_copy': 'Copy one project file; target is old path, value is new path.',
    'folder_create': 'Create a project folder; target is its relative path.',
    'file_run': 'Run a named program in Docker; input is optional newline-separated program input.',
    'terminal': 'Execute an explicitly requested command inside project Docker; value is command, target is optional relative cwd.',
    'automation_create': 'Create an explicitly requested interval task; target is name, value is recurring goal, input is interval seconds >=60.',
    'automation_list': 'List persisted recurring application tasks.',
    'automation_pause': 'Pause/resume a recurring task; target is ID, value is true/false.',
    'automation_delete': 'Delete a recurring task; target is ID.',
}


class ApplicationTools:
    def __init__(self, service, workspace_id=None, job=None, document_ids=None, goal=None, history=None):
        self.service = service
        self.workspace_id = workspace_id
        self.job = job or Job('agent')
        self.document_ids = document_ids
        self.goal = goal
        self.history = history
        self.created_project_id = None
        self.registry = ToolRegistry()
        for name in OPERATIONS:
            self.registry.register(name, lambda target, value='', input='', operation=name:
                                   self._execute(operation, target, value, input),
                                   ToolContract(('target', 'value', 'input'), ('target',),
                                                timeout_seconds=300, max_input_bytes=16000))

    def _workspace(self):
        if not self.workspace_id:
            raise WorkbenchError('needs_input', 'Choose a project for this operation')
        self.service.coding.get(self.workspace_id)
        return self.workspace_id

    def _document(self, name):
        matches = [doc for doc in self.service.documents()
                   if doc['display_name'].casefold() == name.casefold()
                   or doc['document_id'] == name]
        if len(matches) != 1:
            raise WorkbenchError('needs_input', 'Name one unique Knowledge document for this operation')
        return matches[0]

    def _execute(self, operation, target, value, input):
        if self.job.cancel.is_set():
            raise WorkbenchError('cancelled', 'Task stopped before application operation')
        if operation == 'project_create':
            result=self.service.coding.create(target)
            self.workspace_id=result['workspace_id']
            self.created_project_id=self.workspace_id
            return result
        if operation == 'project_delete':
            workspace=self._workspace()
            selected=self.service.coding.get(workspace)
            if target not in {workspace,selected['name']}:
                raise WorkbenchError('needs_input','Name the selected project to delete')
            result=self.service.coding.delete(workspace)
            self.workspace_id=None
            return result
        if operation.startswith('automation_'):
            if operation == 'automation_list':return {'automations':self.service.automations.list()}
            if operation == 'automation_create':
                try:interval=int(input)
                except ValueError:raise WorkbenchError('tool_input', 'Specify the recurring interval in seconds')
                return self.service.automations.create(target,value,interval,self.workspace_id,self.document_ids)
            if operation == 'automation_pause' and value not in {'true','false'}:
                raise WorkbenchError('tool_input', 'Pause must be true or false')
            return self.service.automations.change(target,paused=value=='true',delete=operation=='automation_delete')
        if operation == 'document_create':
            if Path(target).name != target or Path(target).suffix.lower() not in {'.txt', '.md'}:
                raise WorkbenchError('invalid_file', 'Create a text or Markdown document with a simple filename')
            names={doc['display_name'].casefold() for doc in self.service.documents()}
            path = self.service.sources_dir / target
            if path.exists() or path.is_symlink() or target.casefold() in names:
                if re.search(re.escape(target),self.goal or '',re.I):
                    raise WorkbenchError('workspace_conflict', 'A Knowledge document named '+target+' already exists. Ask to update it or choose a new name.')
                base=Path(target)
                for number in range(2,1000):
                    candidate=f'{base.stem}_{number}{base.suffix}'
                    path=self.service.sources_dir/candidate
                    if candidate.casefold() not in names and not path.exists() and not path.is_symlink():break
                else:raise WorkbenchError('workspace_conflict','No available Knowledge document name; choose a different name')
            if re.search(r'\b(?:explain|explaining|describe|describing|about)\b',self.goal or '',re.I) and not re.search(r'\b(?:exactly|verbatim|containing|with the text)\b',self.goal or '',re.I):
                generator=getattr(self.service.model,'document_text',None)
                if callable(generator):
                    if not self.service.ask_lock.acquire(blocking=False):raise WorkbenchError('busy','Another model task is running')
                    try:
                        self.service._lease('text')
                        value=generator(self.goal,'',path.name)
                    finally:self.service.ask_lock.release()
            if self.job.cancel.is_set():raise WorkbenchError('cancelled','Task stopped before creating the document')
            if not value.strip() or len(value.encode('utf-8')) > 128000:
                raise WorkbenchError('invalid_file', 'Provide document text under 128 KB')
            with path.open('x', encoding='utf-8') as source:
                source.write(value)
            return self.service.import_file(path)
        if operation == 'document_update':
            doc = self._document(target)
            if doc.get('source_extension') not in {'.txt', '.md'}:
                raise WorkbenchError('unsupported_file', 'Text updates support TXT and Markdown; replace other formats through Knowledge.')
            generator = getattr(self.service.model, 'document_text', None)
            if callable(generator):
                original = self.service.sources_dir / (doc['active_hash'] + doc['source_extension'])
                if not original.is_file():
                    raise WorkbenchError('source_missing', 'The current document snapshot is missing')
                current = original.read_text(encoding='utf-8-sig')
                if len(current.encode('utf-8')) > 32000:
                    raise WorkbenchError('context_budget', 'This document exceeds the bounded text-edit input budget')
                if not self.service.ask_lock.acquire(blocking=False):
                    raise WorkbenchError('busy', 'Another model task is running')
                try:
                    self.service._lease('text')
                    value = generator(self.goal, current, doc['display_name'])
                finally:
                    self.service.ask_lock.release()
            if self.job.cancel.is_set():
                raise WorkbenchError('cancelled', 'Task stopped before publishing the update')
            if not value.strip() or len(value.encode('utf-8')) > 128000:
                raise WorkbenchError('invalid_file', 'Provide document text under 128 KB')
            # Publish a new source/version; original snapshots and document identity survive.
            from uuid import uuid4
            path = self.service.sources_dir / (uuid4().hex + doc['source_extension'])
            path.write_text(value, encoding='utf-8')
            try:
                return self.service.import_file(path, document_id=doc['document_id'],
                    display_name=doc['display_name'], expected_hash=doc['active_hash'])
            finally:
                path.unlink(missing_ok=True)
        if operation == 'document_import':
            path = self.service.coding._file(self._workspace(), target)
            if not path.is_file():
                raise WorkbenchError('invalid_file', 'Choose an existing project file to add to Knowledge')
            return self.service.import_file(path)
        if operation in {'document_duplicates', 'document_deduplicate'}:
            if target.casefold() != 'knowledge' or value or input:
                raise WorkbenchError('tool_input', 'Duplicate operations require the Knowledge library target and no extra fields')
            # Reference connection is independent of an explicit library management command.
            with self.service.import_lock:
                return self.service.store.exact_duplicates(remove=operation == 'document_deduplicate')
        if operation.startswith('document_'):
            doc = self._document(target)
            identifier = doc['document_id']
            # Optimistic guards keep a plan from silently modifying a newer version.
            version = doc.get('active_hash')
            if operation == 'document_delete':
                return self.service.remove_document(identifier, version)
            if operation == 'document_rename':
                return self.service.rename_document(identifier, value, version)
            if operation == 'document_move':
                return self.service.move_document(identifier, value, version)
            return self.service.copy_document(identifier, value or None, version)
        workspace = self._workspace()
        if operation == 'file_edit':
            if not isinstance(self.goal,str) or not self.goal.strip():
                raise WorkbenchError('tool_input', 'Code edits require the original current user request')
            # A tool plan describes operations, never authors their implementation.
            # Its value may contain hallucinated or escaped source; ignore it.
            # Preserve the complete user request within the public 8,000-character
            # budget. Target is a separate argument; application operations run
            # separately after this code-authoring workflow returns.
            # A newly created project is its own root. Let the project planner
            # choose relative paths from the full request instead of treating
            # a tool-planned prefix as a directory inside that project.
            if workspace==self.created_project_id:target=''
            return self.service.run_coding_project_task(workspace, target, self.goal, job=self.job, routed=True,
                **({'history':self.history} if self.history else {}))
        if operation in {'file_delete', 'file_delete_scope', 'file_move', 'file_copy', 'folder_create'}:
            raise WorkbenchError('tool_input', 'File organization is staged as one reviewed plan, not executed one operation at a time')
        if len(input.encode('utf-8')) > 8000:
            raise WorkbenchError('tool_input', 'Program input exceeds its 8 KB budget')
        if input:
            self.job.input.put_nowait(input if input.endswith('\n') else input + '\n')
        if operation == 'file_run':
            return self.service.execute_coding_file(workspace, target, job=self.job)
        if not value.strip() or len(value) > 2000:
            raise WorkbenchError('tool_input', 'Provide a terminal command under 2,000 characters')
        return self.service.execute_terminal(workspace, value, self.job, cwd=target)

    def execute(self, operations, task):
        if not isinstance(operations, list) or not 1 <= len(operations) <= 8:
            raise WorkbenchError('tool_input', 'Use between one and eight application operations')
        # Validate the entire plan before its first write.
        for operation in operations:
            if not isinstance(operation, dict) or set(operation) != {'tool', 'target', 'value', 'input'} or \
                    operation['tool'] not in OPERATIONS or any(not isinstance(value, str) for value in operation.values()):
                raise WorkbenchError('tool_input', 'Invalid application operation')
        from router.tool_registry import explicit_operation_requested
        from router.telemetry import CURRENT_ROUTE
        trace=CURRENT_ROUTE.get()
        for operation in operations:
            if not explicit_operation_requested(self.goal,operation['tool']):
                if trace:
                    trace.failure_layer='policy'
                    trace.tool_candidates=[{'name':operation['tool'],'status':'rejected','reason':'Not requested in the current user instruction'}]
                    trace.event('TOOL_POLICY_REJECTED')
                raise WorkbenchError('needs_input','The current request does not authorize '+operation['tool'].replace('_',' ')+'. Specify the operation and its target.')
        # One coding workflow already sees the whole current request and can
        # edit several related files atomically. Repeating file_edit for each
        # planned path regenerates the entire project and may undo the first
        # edit or overwrite it with a second model answer.
        if sum(operation['tool']=='file_edit' for operation in operations)>1:
            first=next(i for i,operation in enumerate(operations) if operation['tool']=='file_edit')
            operations=[operation for i,operation in enumerate(operations)
                        if operation['tool']!='file_edit' or i==first]
        # A small model may mistake "create code in a folder" for mkdir only.
        # Recover the requested source-generation operation generically; a
        # directory by itself cannot satisfy a request for new program files.
        if (operations and all(operation['tool'] in {'folder_create','project_create'} for operation in operations)
                and re.search(r'\b(?:create|generate|write|build|make)\b.{0,100}\b(?:code|codes|program|programs|script|scripts|html|css|webpage|website)\b', self.goal or '', re.I)):
            operations=[operation for operation in operations if operation['tool']=='project_create']
            operations.append({'tool':'file_edit','target':'','value':self.goal,'input':''})
        if any(operation['tool']=='file_edit' for operation in operations):
            # The project-wide coding plan creates the requested directory as
            # part of its staged change. A separate mkdir can conflict with an
            # existing folder or write before review.
            operations=[operation for operation in operations if operation['tool']!='folder_create']
        organization={'file_delete','file_delete_scope','file_move','file_copy','folder_create'}
        if operations and all(operation['tool'] in organization for operation in operations):
            workspace=self._workspace()
            broad_delete=bool(re.search(r'\b(?:delete|remove)\b.{0,100}\b(?:all|every)\b|\b(?:all|every)\b.{0,100}\b(?:delete|remove)\b',self.goal or '',re.I))
            if broad_delete and not any(operation['tool']=='file_delete_scope' for operation in operations):
                if re.search(r'\b(?:except|excluding|apart from|other th[ae]n|but keep)\b', self.goal or '', re.I):
                    raise WorkbenchError('generation_format','The planner did not identify the folder to preserve. No files were changed; name that folder exactly and retry.')
                operations=[{'tool':'file_delete_scope','target':'all','value':'','input':''}]
            try:
                sandbox=self.service._verified_coding_sandbox()
            except WorkbenchError as exc:
                if exc.code!='sandbox_unavailable': raise
                sandbox=None
            if self.job:
                self.job.progress('Staging project file organization')
                if sandbox is not None:
                    sandbox.cancel_event=self.job.cancel
                    sandbox.on_output=self.job.append
            result=self.service.coding.stage_file_operations(workspace,operations,sandbox,self.service.tasks,
                                                              cancel=self.job.cancel)
            affected=[change['path'] for change in result.get('changes',[]) if change['action'] in {'create','delete'}]
            paths=', '.join(affected) if len(affected)<=5 else f'{len(affected)} files'
            answer=('The requested folder already exists; no project files were changed.' if result.get('already_exists') else
                    ('Staged '+paths+' for review. Accept changes to save this deletion to the project.' if result['state']=='completed' else
                     'File organization did not pass validation; project files are unchanged.'))
            return {'state':result['state'],'answer':answer,'workspace_id':workspace,
                    'operations':[{'tool':'file_organization','target':result.get('target',''), 'result':result}]}
        if trace:
            trace.tool_candidates=[{'name':operation['tool'],'status':'eligible','reason':'Current operation wording checked; target and scope validated by tool'} for operation in operations]
        results = []
        for index,operation in enumerate(operations):
            self.job.progress('Using ' + operation['tool'].replace('_', ' '))
            result = self.registry.execute(operation['tool'], {key: operation[key] for key in ('target', 'value', 'input')})
            if trace:
                trace.tool_candidates[index]['status']='failed' if result.get('state',result.get('status'))=='failed' else 'executed'
                trace.event('TOOL_COMPLETED' if trace.tool_candidates[index]['status']=='executed' else 'TOOL_FAILED')
            self.service.tasks.step(task, operation['tool'], {'target':operation['target']})
            results.append({'tool':operation['tool'], 'target':operation['target'], 'result':result})
            if result.get('state', result.get('status')) == 'failed':
                return {'state':'failed', 'answer':'The operation failed; later operations were not run.', 'operations':results}
        def summary(result):
            actual_target=(result['result'].get('display_name',result['target'])
                           if result['tool']=='document_create' else result['target'])
            label=result['tool'].replace('_', ' ') + ' ' + actual_target
            if result['tool'] in {'document_duplicates', 'document_deduplicate'}:
                data=result['result']
                return ('Removed '+str(data['removed_count'])+' exact duplicate Knowledge entries; kept one per group and all source files'
                        if result['tool']=='document_deduplicate' else
                        'Found '+str(data['duplicate_count'])+' exact duplicate Knowledge entries in '+str(len(data['groups']))+' groups')
            if result['tool'] == 'automation_list':
                return 'Recurring tasks: ' + '; '.join(item['name']+' ('+item['id']+')'+(' paused' if item['paused'] else ' active')
                    for item in result['result']['automations'])
            if result['tool'] == 'automation_create':label+=' ('+result['result']['id']+')'
            if result['tool'] in {'file_edit','file_organization'} and result['result'].get('changes'):
                paths=[change['path'] for change in result['result']['changes']
                       if change['action'] in {'create','edit'}]
                if paths:
                    label='project files '+', '.join(paths)
                    if not result['result'].get('checks',{}).get('container_executed'):
                        label+=' (staged; Docker validation not run)'
            if result['tool'] in {'file_run','terminal'}:
                label+='; exit '+str(result['result'].get('exit_code'))+'\n'+result['result'].get('stdout','')[-4000:]
            return label
        prefix=('Staged for review: ' if any(item['result'].get('publication_state')=='staged' and item['result'].get('changes') for item in results)
                else 'Completed: ')
        return {'state':'completed', 'answer':prefix + '; '.join(summary(result) for result in results) + '.',
            'workspace_id':self.workspace_id,'operations':results}
