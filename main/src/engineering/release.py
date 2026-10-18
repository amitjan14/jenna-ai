"""Content-addressed manifests and measurable release gates."""
from main.src.tools.llm import get_client
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[3]
VERSION='0.2.0'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def manifest():
    files=sorted([*ROOT.glob('main/src/**/*.py'),*ROOT.glob('main/instructions/*.md'),*ROOT.glob('evaluation/**/*.py'),
                  *ROOT.glob('scripts/*.py'),*ROOT.glob('evaluation/datasets/*'),*ROOT.glob('.github/workflows/*'),
                  *ROOT.glob('postman/*.json'),ROOT/'main/mcp/servers.json',ROOT/'requirements.lock.txt',ROOT/'.env.example'])
    fingerprints={str(path.relative_to(ROOT)):sha(path) for path in files if path.is_file()}
    packages={}
    for line in (ROOT/'requirements.lock.txt').read_text().splitlines():
        if '==' not in line:
            continue
        name=line.split('==')[0].split('[')[0]
        try:
            packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name]=None
    revision=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True)
    models={}
    try:
        models={model.model:model.digest for model in get_client(timeout=3).list().models}
    except Exception:
        pass
    content_digest=hashlib.sha256(json.dumps(fingerprints,sort_keys=True).encode()).hexdigest()
    return {
        'version':VERSION,
        'created_at':datetime.now(timezone.utc).isoformat(),
        'revision':revision.stdout.strip() if revision.returncode==0 else None,
        'content_sha256':content_digest,
        'files':fingerprints,
        'dependencies':packages,
        'model_digests':models,
        'configuration':{key:os.getenv(key) for key in [
            'JENNA_CHAT_MODEL',
            'JENNA_ROUTER_MODEL',
            'JENNA_MCP_MODEL',
            'JENNA_MCP_CONTEXT_TOKENS',
            'JENNA_MCP_MAX_STEPS',
            'JENNA_MCP_MAX_READS',
            'JENNA_CHUNKING_STRATEGY',
            'JENNA_PDF_PARSER'
        ]}
    }


def behavior_fingerprint_matches(previous,current):
    def behavior(files):
        return {key:value for key,value in files.items() if not key.startswith(('.github/','postman/'))
                and key not in {'main/src/engineering/release.py','scripts/release_check.py'}}
    return bool(previous.get('files')) and behavior(previous['files'])==behavior(current['files'])


def gate(candidate,baseline=None,min_success=.8,max_p95=None):
    summary=candidate.get('summary',{})
    rows=candidate.get('results',[])
    total=summary.get('total',0)
    current=manifest()
    old=candidate.get('manifest',{})
    # Verification/CI changes do not alter model inference. Keep their complete
    # hashes in both manifests, but gate measured behavior on the runtime files.
    model=candidate.get('model')
    previous_digest=old.get('model_digests',{}).get(model)
    current_digest=current.get('model_digests',{}).get(model)
    checks={
        'complete':bool(summary.get('complete')),
        'nonempty':total>0,
        'success':total>0 and summary.get('passed',0)/total>=min_success,
        'dataset_current':candidate.get('dataset_sha256')==sha(ROOT/'evaluation/datasets/agent_generalization.jsonl'),
        'behavior_current':behavior_fingerprint_matches(old,current),
        'model_current':bool(previous_digest) and previous_digest==current_digest}
    if baseline:
        checks['same_dataset']=candidate.get('dataset_sha256')==baseline.get('dataset_sha256')
        checks['same_split']=candidate.get('split')==baseline.get('split')
        checks['nonregression']=summary.get('passed',0)/max(1,total)>=baseline.get('summary',{}).get('passed',0)/max(1,baseline.get('summary',{}).get('total',0))
    times=sorted(row['metrics']['total_seconds'] for row in rows if row.get('metrics'))
    if max_p95 is not None:
        checks['latency']=bool(times) and times[max(0,__import__('math').ceil(.95*len(times))-1)]<=max_p95
    return {
        'passed':all(checks.values()),
        'checks':checks,
        'thresholds':{
            'min_success':min_success,
            'max_p95_seconds':max_p95
        }
    }
