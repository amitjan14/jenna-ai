"""Small TTL cache for stable read metadata, scoped to connection credentials."""
from copy import deepcopy
import hashlib
import json
import os
import threading
import time


class TTLCache:
    def __init__(self,max_entries=128):self.entries={};self.lock=threading.Lock();self.max_entries=max_entries
    def get(self,key):
        with self.lock:
            entry=self.entries.get(key)
            if not entry:return None
            if entry[0]<=time.monotonic():self.entries.pop(key,None);return None
            return deepcopy(entry[1])
    def put(self,key,value,ttl):
        if ttl<=0:return
        with self.lock:
            if len(self.entries)>=self.max_entries:self.entries.pop(next(iter(self.entries)))
            self.entries[key]=(time.monotonic()+ttl,deepcopy(value))


metadata_cache=TTLCache()


def credential_key(config,name):
    from main.src.integrations.mcp_auth import token_storage
    auth=config.get('auth',{'type':'none'})
    material={'config':config,'environment':{key:os.getenv(ref,'') for key,ref in auth.items() if key.endswith('_env')}}
    if auth.get('type')=='oauth':
        directory=token_storage(name).directory
        material['oauth_versions']=[(directory/f).stat().st_mtime_ns if (directory/f).exists() else None for f in ['tokens.json','client.json']]
    return hashlib.sha256(json.dumps(material,sort_keys=True).encode()).hexdigest()
