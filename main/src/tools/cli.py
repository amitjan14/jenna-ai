"""Local service diagnostics and a terminal client for Jenna."""
from main.src.utils.enums import Intent, PdfParser, SearchMode
from main.src.utils.constants import DEFAULT_CHAT_MODEL
import argparse
import importlib.metadata
import json
import os


def doctor():
    import ollama
    from main.src.utils.constants import CHAT_MODEL,ROUTER_MODEL,EMBEDDING_MODEL
    report={'models':{},'dependencies':{},'web_configured':bool(os.getenv('TAVILY_API_KEY'))}
    for package in ['streamlit','ollama',PdfParser.PYPDF,'chromadb','sentence-transformers','faster-whisper','kokoro']:
        try: report['dependencies'][package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: report['dependencies'][package]=None
    try:
        tags=ollama.Client(host=os.getenv('OLLAMA_HOST','http://localhost:11434'),timeout=5).list()
        installed={m.model for m in tags.models}
        for model in {CHAT_MODEL,ROUTER_MODEL,EMBEDDING_MODEL,os.getenv('JENNA_MCP_MODEL',DEFAULT_CHAT_MODEL)}:
            report['models'][model]=model in installed or model+':latest' in installed
    except Exception as error:
        report['ollama_error']=type(error).__name__
    report['ready']=bool(report['models']) and all(report['models'].values()) and all(
        report['dependencies'][p] for p in ['streamlit','ollama',PdfParser.PYPDF,'chromadb','sentence-transformers'])
    print(json.dumps(report,indent=2))
    return 0 if report['ready'] else 1


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor')
    from main.src.tools.mcp_server import add_arguments
    add_arguments(sub.add_parser('mcp',help='Serve Jenna to MCP clients'))
    chat=sub.add_parser(Intent.CHAT);chat.add_argument('question');chat.add_argument('--mode',choices=[SearchMode.AUTO,SearchMode.DOCUMENTS,SearchMode.WEB,SearchMode.DOCUMENTS_AND_WEB],default=SearchMode.AUTO)
    args=p.parse_args()
    if args.command=='doctor':return doctor()
    if args.command=='mcp':
        from main.src.tools.mcp_server import serve
        serve(args)
        return 0
    from main.src.agent.assistant_service import run_assistant
    result=run_assistant(args.question,mode=args.mode)
    print(json.dumps(result,indent=2))
    return 1 if result['status'].endswith('_error') else 0


if __name__=='__main__':raise SystemExit(main())
