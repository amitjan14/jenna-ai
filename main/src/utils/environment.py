"""Literal local web credential lookup without executing shell configuration."""
import os
from pathlib import Path

LOCAL_ENV_FILE = Path(__file__).resolve().parents[3] / '.env'


def tavily_api_key():
    """An explicit environment value wins, including empty to disable web access."""
    configured = os.environ.get('TAVILY_API_KEY')
    if configured is not None:
        return configured.strip()
    try:
        lines = LOCAL_ENV_FILE.read_text(encoding='utf-8-sig').splitlines()
    except OSError:
        return ''
    value = ''
    for line in lines:
        line = line.strip()
        if line.startswith('export '):
            line = line[7:].lstrip()
        name, separator, candidate = line.partition('=')
        if separator and name.strip() == 'TAVILY_API_KEY':
            candidate = candidate.strip()
            if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in {'"', "'"}:
                candidate = candidate[1:-1]
            value = candidate.strip()
    return value
