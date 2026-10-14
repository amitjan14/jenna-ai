import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx2
from mcp.shared.auth import OAuthToken, OAuthClientInformationFull
from main.src.integrations.mcp_auth import FileTokenStorage, oauth_provider, token_storage


class RefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_cached_expiry_is_restored_across_provider_instances(self):
        with tempfile.TemporaryDirectory() as temp:
            storage = FileTokenStorage(temp)
            await storage.set_tokens(OAuthToken(access_token='fixture', expires_in=3600))
            provider = oauth_provider({'url': 'https://fixture.example/mcp'}, storage)
            await provider._initialize()
            self.assertTrue(provider.context.is_token_valid())
            self.assertAlmostEqual(provider.context.token_expiry_time,
                (Path(temp) / 'tokens.json').stat().st_mtime + 3570, delta=1)

    async def test_expired_cache_discovers_registered_issuer_before_refresh(self):
        with tempfile.TemporaryDirectory() as temp:
            storage = FileTokenStorage(temp)
            await storage.set_tokens(OAuthToken(access_token='fixture', refresh_token='fixture-refresh', expires_in=60))
            token_file = Path(temp) / 'tokens.json'
            os.utime(token_file, (time.time()-3600, time.time()-3600))
            await storage.set_client_info(OAuthClientInformationFull(client_id='fixture-client',
                redirect_uris=['http://127.0.0.1:8766/callback'], issuer='https://issuer.example', token_endpoint_auth_method='none'))
            observed = []
            class MetadataClient:
                def __init__(self, **kwargs): pass
                async def __aenter__(self): return self
                async def __aexit__(self, *args): pass
                async def get(self, url):
                    observed.append(url)
                    return httpx2.Response(200, json={'issuer':'https://issuer.example',
                        'authorization_endpoint':'https://issuer.example/authorize',
                        'token_endpoint':'https://issuer.example/oauth/token', 'response_types_supported':['code']})
            with patch('main.src.integrations.mcp_auth.httpx2.AsyncClient', MetadataClient):
                provider = oauth_provider({'url':'https://resource.example/mcp'}, storage)
                await provider._initialize()
            self.assertFalse(provider.context.is_token_valid())
            self.assertTrue(observed)
            request = await provider._refresh_token()
            self.assertEqual(str(request.url), 'https://issuer.example/oauth/token')
            self.assertNotIn('resource.example', str(request.url))

    async def test_relative_memory_path_matches_application_storage(self):
        with patch.dict('os.environ', {'JENNA_MEMORY_PATH':'fixture-memory'}):
            directory = token_storage('jira').directory
        expected = Path(__file__).resolve().parents[2] / 'main/fixture-memory/mcp_oauth/jira'
        self.assertEqual(directory, expected)


if __name__ == '__main__': unittest.main()
