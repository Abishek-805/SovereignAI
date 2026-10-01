"""Content checks for generated source, independent of container syntax checks."""
import ast
import re
from html.parser import HTMLParser
from pathlib import Path


class _Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = 0

    def handle_starttag(self, tag, attrs):
        self.elements += 1

    def handle_startendtag(self, tag, attrs):
        self.elements += 1


def source_issue(path, content):
    """Reject unusable source before generation finishes; sandbox checks still follow."""
    suffix = Path(path).suffix.lower()
    if not content.strip():
        return 'The file is empty.'
    if suffix in {'.md', '.txt', '.json'}:
        return None
    if suffix in {'.html', '.htm'}:
        parser = _Markup()
        parser.feed(content)
        return None if parser.elements else 'HTML requires actual markup elements, not only comments or prose.'
    if suffix == '.py':
        try:
            tree = ast.parse(content)
        except SyntaxError as exc:
            return f'Python syntax error on line {exc.lineno}: {exc.msg}.'
        statements = [node for node in tree.body if not (isinstance(node, ast.Expr)
                      and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str))]
        return None if statements else 'Python requires statements beyond comments and documentation strings.'
    # Match string literals before comments so comment delimiters in strings
    # remain source. This is a content gate, not a replacement language parser.
    line_comment = r'--[^\n]*' if suffix == '.sql' else (r'\#[^\n]*' if suffix in {'.sh', '.bash'} else r'//[^\n]*')
    tokens = re.compile(r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|/\*.*?\*/|''' + line_comment, re.S)
    def strip_comment(match):
        text = match.group()
        return text if text[0] in {'"', "'", '`'} else ''
    remaining = tokens.sub(strip_comment, content).strip()
    if suffix == '.css':
        if not (re.search(r'\{[^{}]*[\w-]+\s*:\s*[^;}]+', remaining, re.S)
                or re.search(r'@(import|charset|namespace)\b[^;]+;', remaining, re.I)):
            return 'CSS requires a style declaration or a stylesheet directive.'
    return None if remaining else 'The source contains only comments.'


def intentional_non_source(instruction, path, operation_count):
    """Only a direct user request can authorize empty or comment-only output."""
    named = re.search(r'(?<![\w./-])' + re.escape(path) + r'(?![\w./-])', instruction, re.I)
    return bool((named or operation_count == 1) and re.search(
        r'\b(?:empty|blank)\s+(?:file|stylesheet|module)|\b(?:comment[- ]only|only\s+comments)\b', instruction, re.I))


def generated_source_issue(path, content, instruction, before=None, operation_count=1):
    """Apply shared user-intent exceptions to both generation workflows."""
    if intentional_non_source(instruction, path, operation_count):
        return None
    if (before is not None and before.strip() and source_issue(path, before)
            and content.strip() and re.search(r'\bcomments?\b', instruction, re.I)):
        return None
    return source_issue(path, content)
