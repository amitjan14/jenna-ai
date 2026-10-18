"""Budgeted tool schemas and structured context compaction."""
from main.src.utils import instructions
from main.src.utils.enums import Role
from main.src.utils.constants import DEFAULT_MCP_CONTEXT_TOKENS
from main.src.utils import regex_constants as rx
import json
import re


def tokens(text):
    return set(re.findall(rx.TOOL_TOKEN,text.lower()))


def select_tools(question,tools,history=None,limit=8):
    if not 1<=limit<=16:
        raise ValueError('Tool schema limit must be 1–16')
    if len(tools)<=limit:
        return list(tools),[]
    terms=tokens(question+' '+ ' '.join(m.get('content','')[-1000:] for m in (history or [])[-2:]))
    scores=[]
    for index,tool in enumerate(tools):
        words=tokens(re.sub(rx.CAMEL_CASE_BOUNDARY,rx.CAMEL_CASE_REPLACEMENT,tool.name)+' '+(tool.description or ''))
        scores.append((len(terms&words),-index,tool))
    ranked=[item[2] for item in sorted(scores,key=lambda x:(x[0],x[1]),reverse=True)]
    foundational=[tool for tool in tools if tool.name in {'getAccessibleAtlassianResources','getJiraCurrentUser'}]
    selected=[]
    for tool in foundational+ranked:
        if tool not in selected:
            selected.append(tool)
        if len(selected)>=limit:
            break
    return selected,[tool for tool in tools if tool not in selected]


def summarize_history(history,max_chars=4000):
    older=(history or [])[:-6]
    if not older:
        return ''
    references=[]
    for message in older:
        text=message.get('content','')
        if not isinstance(text,str):
            continue
        # Extract references without inventing a semantic summary of old facts.
        ids=re.findall(rx.HISTORY_IDENTIFIER,text)
        references.extend(ids)
    return json.dumps({
        'older_turn_count': len(older),
        'references': list(dict.fromkeys(references))[:60]
    })[:max_chars]


def fit_messages(messages,definitions,context_tokens=DEFAULT_MCP_CONTEXT_TOKENS,reserved_output=2048,question=None):
    # Conservative characters estimate. Exact tokenizer counts are also measured
    # by Ollama; this guard avoids depending on model-specific Python tokenizers.
    budget=max(4000,(context_tokens-reserved_output)*3-len(json.dumps(definitions)))
    size=lambda m:len(json.dumps(m,ensure_ascii=False))
    if sum(map(size,messages))<=budget:
        return messages,False
    system=messages[0]
    current={
        'role': Role.USER,
        'content': question
    } if question else next((m for m in messages[1:] if m.get('role')==Role.USER),messages[1])
    tail=[]
    remaining=budget-size(system)-size(current)-600
    # Keep complete assistant/tool groups. Never split a JSON tool result into
    # malformed text, and never leave tool results without their assistant call.
    groups=[]
    group=[]
    for message in messages[2:]:
        if message.get('role')!='tool' and group:
            groups.append(group)
            group=[]
        group.append(message)
    if group:
        groups.append(group)
    for group in reversed(groups):
        total=sum(map(size,group))
        if total>remaining:
            break
        tail=group+tail
        remaining-=total
    note={
        'role': Role.USER,
        'content': instructions.CONTEXT_OMITTED
    }
    return [system,current,note,*tail],True
