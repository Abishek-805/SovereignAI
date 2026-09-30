import pytest

from workflows.source_quality import source_issue


@pytest.mark.parametrize('path,content', [('a.py', '# implement later'), ('a.js', '/* later */'),
    ('a.css', '/* later */'), ('a.html', '/* later */'), ('a.html', '<!-- later -->'),
    ('a.html', 'Here is the requested page'), ('a.py', '"""module documentation"""')])
def test_generated_source_requires_language_content(path, content):
    assert source_issue(path, content)


@pytest.mark.parametrize('path,content', [('a.py', 'print("# text")'),
    ('a.js', 'console.log("/* text */")'), ('a.html', '<p>Hello</p>'),
    ('a.css', 'body { color: red; }'), ('README.md', '# Notes'), ('notes.txt', 'Notes'),
    ('a.json', '{}')])
def test_valid_source_and_documents(path, content):
    assert source_issue(path, content) is None
