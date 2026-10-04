"""Deterministic document containers; model output is data, never executable code."""
import json,re
from pathlib import Path
from backend.contracts import WorkbenchError


def generate(path, specification):
    path=Path(path)
    if not isinstance(specification,dict):raise WorkbenchError('generation_format','Expected a structured document object')
    if path.exists():raise WorkbenchError('workspace_conflict','Generated document already exists')
    suffix=path.suffix.lower()
    try:
        if suffix=='.docx':
            from docx import Document
            doc=Document()
            title=specification.get('title','')
            if title:doc.add_heading(str(title),0)
            sections=specification.get('sections',[])
            if not isinstance(sections,list) or not sections:raise ValueError('At least one section required')
            for section in sections[:64]:
                if section.get('heading'):doc.add_heading(str(section['heading']),1)
                for paragraph in section.get('paragraphs',[])[:128]:doc.add_paragraph(str(paragraph))
                for rows in section.get('tables',[])[:16]:
                    if isinstance(rows,dict):
                        headers=rows.get('headers',rows.get('columns',[]))
                        rows=([headers] if headers else [])+rows.get('rows',[])
                    if not rows or not isinstance(rows,list) or any(not isinstance(row,list) for row in rows):raise ValueError('Invalid table')
                    width=max(len(row) for row in rows)
                    table=doc.add_table(rows=len(rows),cols=width)
                    table.style='Table Grid'
                    for i,row in enumerate(rows):
                        for j,value in enumerate(row):table.cell(i,j).text=str(value)
            doc.save(path)
            reopened=Document(path)
            if not any(p.text.strip() for p in reopened.paragraphs):raise ValueError('Document is empty')
            return {'opened':True,'paragraphs':len(reopened.paragraphs),'tables':len(reopened.tables)}
        if suffix=='.xlsx':
            from openpyxl import Workbook,load_workbook
            workbook=Workbook();workbook.remove(workbook.active)
            sheets=specification.get('sheets',[])
            if not isinstance(sheets,list) or not sheets:raise ValueError('At least one sheet required')
            for sheet in sheets[:32]:
                ws=workbook.create_sheet(str(sheet['name']))
                rows=sheet.get('rows',[])
                if not rows:raise ValueError('Sheet rows required')
                for row in rows[:10000]:
                    if not isinstance(row,list) or len(row)>256:raise ValueError('Invalid worksheet row')
                    for value in row:
                        if not isinstance(value,(str,int,float,bool,type(None))):raise ValueError('Unsupported cell type')
                        if isinstance(value,str) and value.startswith('=') and ('[' in value or '://' in value or 'DDE' in value.upper()):raise ValueError('External formulas are not supported')
                    ws.append(row)
                ws.freeze_panes='A2'
            calculations={}
            for ws in workbook:
                for row in ws:
                    for cell in row:
                        formula=cell.value
                        if not isinstance(formula,str) or not formula.startswith('='):continue
                        match=re.fullmatch(r'=SUM\(([A-Z]+[1-9][0-9]*):([A-Z]+[1-9][0-9]*)\)',formula,re.I)
                        if not match:raise ValueError('Unsupported formula in '+ws.title+'!'+cell.coordinate+': '+formula+'; use SUM over numeric cells')
                        values=[item.value for cells in ws[match.group(1)+':'+match.group(2)] for item in cells]
                        numbers=[value for value in values if isinstance(value,(int,float)) and not isinstance(value,bool)]
                        if not numbers or len(numbers)!=len(values):raise ValueError('Formula '+formula+' references empty or nonnumeric cells at '+ws.title+'!'+cell.coordinate+'. Actual numeric cells: '+', '.join(c.coordinate+'='+str(c.value) for r in ws for c in r if isinstance(c.value,(int,float)) and not isinstance(c.value,bool))+'. Repair the formula reference; preserve the requested rows and columns.')
                        calculations[ws.title+'!'+cell.coordinate]=sum(numbers)
            workbook.save(path)
            # Preserve formulas and deterministic calculated values for offline readers.
            if calculations:
                from zipfile import ZipFile,ZIP_DEFLATED
                import xml.etree.ElementTree as ET
                namespace='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
                with ZipFile(path) as archive:parts={name:archive.read(name) for name in archive.namelist()}
                for index,ws in enumerate(workbook,1):
                    name=f'xl/worksheets/sheet{index}.xml'
                    root=ET.fromstring(parts[name])
                    for cell in root.iter(namespace+'c'):
                        key=ws.title+'!'+cell.attrib['r']
                        if key not in calculations:continue
                        value=cell.find(namespace+'v')
                        if value is None:value=ET.SubElement(cell,namespace+'v')
                        value.text=str(calculations[key])
                    parts[name]=ET.tostring(root,encoding='utf-8')
                with ZipFile(path,'w',ZIP_DEFLATED) as archive:
                    for name,data in parts.items():archive.writestr(name,data)
            check=load_workbook(path,data_only=False)
            return {'opened':True,'sheets':check.sheetnames,'computed_formula_values':calculations,'formula_cache_written':True}
        raise ValueError('Supported generated containers are DOCX and XLSX')
    except (ValueError,KeyError,TypeError) as error:
        path.unlink(missing_ok=True)
        raise WorkbenchError('generation_format',str(error)) from error


def specification_schema(suffix):
    cell={'type':['string','number','boolean','null']}
    rows={'type':'array','minItems':1,'items':{'type':'array','items':cell}}
    if suffix=='.xlsx':
        item={'type':'object','properties':{'name':{'type':'string'},'rows':rows},'required':['name','rows'],'additionalProperties':False}
        return {'type':'object','properties':{'sheets':{'type':'array','minItems':1,'items':item}},'required':['sheets'],'additionalProperties':False}
    section={'type':'object','properties':{'heading':{'type':'string'},'paragraphs':{'type':'array','items':{'type':'string'}},'tables':{'type':'array','items':rows}},'required':['heading','paragraphs','tables'],'additionalProperties':False}
    return {'type':'object','properties':{'title':{'type':'string'},'sections':{'type':'array','minItems':1,'items':section}},'required':['title','sections'],'additionalProperties':False}
