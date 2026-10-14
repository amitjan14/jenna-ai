"""A minimal MCP client that connects to Jenna via stdio or local HTTP."""
import argparse
import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[1]


async def use_session(streams, question=None):
    async with ClientSession(*streams, read_timeout_seconds=120) as session:
        initialized=await session.initialize()
        print('Connected:', initialized.server_info.name)
        print('Tools:', ', '.join(tool.name for tool in (await session.list_tools()).tools))
        result=await session.call_tool('calculate',{'expression':'sqrt(81) + 15 / 100 * 200'})
        print(json.dumps(result.structured_content,indent=2))
        if question:
            result=await session.call_tool('ask_jenna',{'question':question,'source_mode':'Documents'})
            print(json.dumps(result.structured_content,indent=2))
            if result.is_error:raise RuntimeError('Jenna returned a tool error')


async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',help='Streamable HTTP URL, e.g. http://127.0.0.1:8765/mcp')
    parser.add_argument('--question',help='Optional question about uploaded PDFs')
    args=parser.parse_args()
    if args.url:
        async with streamable_http_client(args.url) as streams:
            await use_session(streams,args.question)
    else:
        params=StdioServerParameters(command=str(ROOT/'.venv/bin/python'),
                                    args=[str(ROOT/'main/src/tools/mcp_server.py')])
        async with stdio_client(params) as streams:
            await use_session(streams,args.question)


if __name__=='__main__':asyncio.run(main())
