from workflows.coding_workspace import bounded_file_context, MAX_CONTEXT_CHARS
from workflows.project_map import inspect_project
from workflows.code_runtime import runner


def test_new_file_reads_existing_dependency_without_granting_write_scope():
    files={'lib/helper.py':'def answer(): return 42', 'unrelated.py':'x'*MAX_CONTEXT_CHARS}
    assert bounded_file_context(files,'lib/main.py','Use helper.answer')=={'lib/helper.py':files['lib/helper.py']}


def test_target_and_imported_module_take_priority_over_large_unrelated_file():
    files={'main.py':'from helper import answer', 'helper.py':'def answer(): return 42', 'a.py':'x'*MAX_CONTEXT_CHARS}
    assert set(bounded_file_context(files,'main.py'))=={'main.py','helper.py'}


def test_nested_python_entrypoint_uses_package_execution():
    project=inspect_project({'todo/app.py':b'if __name__ == "__main__": print(42)'})
    assert project['commands']['run']=='python -m todo.app'


def test_java_project_launches_package_qualified_class():
    project=inspect_project({'pkg/Main.java':b'package pkg; public class Main { public static void main(String[] args){} }'})
    assert 'java -cp /output/classes pkg.Main' in project['commands']['run']


def test_generated_runtime_wrappers_compile():
    for target in ('pkg/main.py','pkg/Main.java','pkg/main.ts','pkg/main.go'):
        compile(runner(target,'run'),target,'exec')
