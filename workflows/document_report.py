"""Export a grounded document answer as a reviewable Word report."""
import hashlib
import json
import time
from tempfile import TemporaryDirectory
from pathlib import Path
from docx import Document
from backend.contracts import WorkbenchError


def publish_report(settings, task_id, question, result):
    if result.get('status') != 'answered' or not result.get('sources'):
        raise WorkbenchError('missing_evidence','The documents did not support a grounded report. Inspect the answer and sources first.')
    root = settings.data_dir.parent / 'outputs'
    root.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(prefix='.report-',dir=root) as directory:
        folder = Path(directory)
        path = folder / 'Document report.docx'
        doc = Document()
        doc.add_heading('Document report',0)
        doc.add_paragraph(question)
        doc.add_paragraph('AI-assisted draft. Review the cited evidence before use.')
        for paragraph in result['answer'].split('\n'):
            if paragraph.strip(): doc.add_paragraph(paragraph)
        doc.add_heading('Sources',1)
        for source in result['sources']:
            doc.add_paragraph(f"[{source['label']}] {source['display_name']} · page {source.get('page') or 'not recorded'}")
            doc.add_paragraph(source['text'])
        doc.save(path)
        if not Document(path).paragraphs:
            raise WorkbenchError('artifact_invalid','Report could not be read back')
        metadata={'task_id':task_id,'created_at':time.time(),'files':[{'name':path.name,
                  'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}]}
        (folder/'manifest.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
        folder.rename(root/task_id)
    return {'word':f'/artifacts/{task_id}/word'}
