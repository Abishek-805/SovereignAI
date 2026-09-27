import argparse
import json
from pathlib import Path
from backend.contracts import WorkbenchError
from backend.service import Workbench


def main():
    parser=argparse.ArgumentParser(description='SovereignAI local document workbench')
    commands=parser.add_subparsers(dest='command',required=True)
    imp=commands.add_parser('import'); imp.add_argument('path',type=Path); imp.add_argument('--document-id')
    commands.add_parser('documents'); commands.add_parser('status')
    ask=commands.add_parser('ask'); ask.add_argument('question'); ask.add_argument('--document-id',action='append')
    args=parser.parse_args()
    service=Workbench()
    try:
        if args.command=='import': result=service.import_file(args.path,args.document_id)
        elif args.command=='ask': result=service.ask(args.question,args.document_id)
        elif args.command=='documents': result=service.documents()
        else: result=service.status()
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except WorkbenchError as exc:
        print(json.dumps({'code':exc.code,'message':str(exc)}))
        return 1
    finally:
        service.model.close()


if __name__=='__main__':
    raise SystemExit(main())
