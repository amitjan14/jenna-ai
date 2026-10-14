import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT=Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.getenv('JENNA_TEST_HTTP')=='1','Enable explicit local HTTP integration test')
class HTTPIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_clients_connect_to_same_http_server(self):
        with tempfile.TemporaryDirectory(prefix='jenna-http-test-') as memory:
            with socket.socket() as port_socket:
                port_socket.bind(('127.0.0.1',0))
                port=port_socket.getsockname()[1]
            with tempfile.TemporaryFile(mode='w+') as log:
                process=subprocess.Popen([sys.executable,str(ROOT/'main/src/tools/mcp_server.py'),
                    '--transport','streamable-http','--port',str(port),'--memory-path',memory],
                    stdout=log,stderr=log)
                try:
                    for _ in range(100):
                        if process.poll() is not None:
                            log.seek(0);self.fail(log.read())
                        try:
                            reader,writer=await asyncio.open_connection('127.0.0.1',port)
                            writer.close();await writer.wait_closed();break
                        except OSError:await asyncio.sleep(.05)
                    else:self.fail('HTTP server did not become ready')
                    async def client(number):
                        async with streamable_http_client(f'http://127.0.0.1:{port}/mcp') as streams:
                            async with ClientSession(*streams,read_timeout_seconds=20) as session:
                                await session.initialize()
                                tools=await session.list_tools()
                                self.assertIn('calculate',[tool.name for tool in tools.tools])
                                result=await session.call_tool('calculate',{'expression':f'{number} + 1'})
                                self.assertFalse(result.is_error)
                                self.assertEqual(result.structured_content['value'],number+1)
                    await asyncio.gather(client(10),client(20))
                finally:
                    process.terminate()
                    try:process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill();process.wait(timeout=5)


if __name__=='__main__':unittest.main()
