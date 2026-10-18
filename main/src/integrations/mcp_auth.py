"""SDK OAuth storage and an interactive loopback login callback."""
import asyncio
import json
import os
import tempfile
import threading
import webbrowser
import time
import httpx2
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import OAuthClientMetadata, OAuthClientInformationFull, OAuthToken, AuthorizationCodeResult
from mcp.client.auth.oauth2 import (build_oauth_authorization_server_metadata_discovery_urls,
                                   handle_auth_metadata_response, validate_metadata_issuer)


class FileTokenStorage:
    def __init__(self, directory):
        self.directory = Path(directory)

    def read(self, name, model):
        path = self.directory / name
        return model.model_validate_json(path.read_text()) if path.exists() else None

    def write(self, name, model):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(dir=self.directory)
        try:
            with os.fdopen(descriptor, 'w') as output:
                output.write(model.model_dump_json())
            os.replace(temporary, self.directory / name)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    async def get_tokens(self):
        return self.read('tokens.json', OAuthToken)

    async def set_tokens(self, tokens):
        self.write('tokens.json', tokens)

    def token_expiry(self, tokens):
        # File mtime is the receipt time and remains stable across process restarts.
        path = self.directory / 'tokens.json'
        return path.stat().st_mtime + tokens.expires_in - 30 if tokens.expires_in is not None and path.exists() else None

    async def get_client_info(self):
        return self.read('client.json', OAuthClientInformationFull)

    async def set_client_info(self, info):
        self.write('client.json', info)


def token_storage(name):
    root = Path(os.getenv('JENNA_MEMORY_PATH', str(Path(__file__).resolve().parents[2] / 'jenna_memory')))
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[2] / root
    return FileTokenStorage(root / 'mcp_oauth' / name)


class PersistentOAuthProvider(OAuthClientProvider):
    """Restore SDK refresh prerequisites that are otherwise process-local."""
    async def _initialize(self):
        await super()._initialize()
        tokens = self.context.current_tokens
        if not tokens:
            return
        self.context.token_expiry_time = self.context.storage.token_expiry(tokens)
        if self.context.is_token_valid() or not self.context.can_refresh_token():
            return
        # Registered credentials are issuer-bound by the SDK. Discover that
        # issuer's current metadata before refreshing; never send a token to a
        # guessed /token endpoint on the MCP resource host.
        issuer = self.context.client_info.issuer
        if not issuer:
            return
        urls = build_oauth_authorization_server_metadata_discovery_urls(issuer, self.context.server_url)
        async with httpx2.AsyncClient(timeout=15) as client:
            for url in urls:
                response = await client.get(url)
                ok, metadata = await handle_auth_metadata_response(response)
                if ok and metadata:
                    validate_metadata_issuer(metadata, issuer)
                    self.context.auth_server_url = issuer
                    self.context.oauth_metadata = metadata
                    return
        raise RuntimeError('Could not discover the registered OAuth issuer for token refresh. Retry Jira sign-in.')


def oauth_provider(config, storage, redirect=None, callback=None, port=8766):
    async def needs_login(*args):
        raise RuntimeError('MCP sign-in required. Run: .venv/bin/python -m main.src.integrations.mcp_client login jira')
    return PersistentOAuthProvider(
        server_url=config['url'],
        client_metadata=OAuthClientMetadata(
            redirect_uris=[f'http://127.0.0.1:{port}/callback'],
            client_name='Jenna AI',
            token_endpoint_auth_method='none',
            application_type='native'
        ),
        storage=storage,
        redirect_handler=redirect or needs_login,
        callback_handler=callback or needs_login
    )


class LoginCallback:
    """The SDK validates returned state/PKCE; this only receives the code."""
    def __init__(self, port=8766):
        self.port = port
        self.event = threading.Event()
        self.result = None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlsplit(self.path)
                if parsed.path != '/callback':
                    self.send_error(404)
                    return
                query = parse_qs(parsed.query)
                if 'code' not in query or 'state' not in query:
                    self.send_error(400, 'Missing authorization code or state')
                    return
                owner.result = AuthorizationCodeResult(
                    code=query['code'][0],
                    state=query['state'][0],
                    iss=query.get('iss', [None])[0]
                )
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'Jenna received the callback. You can close this tab.')
                owner.event.set()

            def log_message(self, *args):
                pass  # Never log the authorization code.

        self.server = HTTPServer(('127.0.0.1', port), Handler)

    def __enter__(self):
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    async def redirect(self, url):
        print('Opening your browser for MCP sign-in...')
        webbrowser.open(url)

    async def callback(self):
        if not await asyncio.to_thread(self.event.wait, 180):
            raise TimeoutError('MCP sign-in timed out. Run login again.')
        return self.result
