"""Reject leakage, malformed supervision, and truncation before training."""
import argparse
import json
from pathlib import Path


def validate(data, tokenizer, max_length=1536):
    seen={}
    lengths=[]
    errors=[]
    for split in ['train','valid','test']:
        path=data/f'{split}.jsonl'
        rows=[json.loads(line) for line in path.read_text().splitlines()]
        if not rows: errors.append(f'{split}: empty split')
        for index,row in enumerate(rows):
            messages=row['messages']
            if [m['role'] for m in messages]!=['system','user','assistant']:
                errors.append(f'{split}:{index}: invalid role sequence')
            key=(row['task'],messages[1]['content'])
            if key in seen: errors.append(f'{split}:{index}: duplicate with {seen[key]}')
            seen[key]=split
            full=tokenizer.apply_chat_template(messages,tokenize=True)
            prompt=tokenizer.apply_chat_template(messages[:-1],tokenize=True,add_generation_prompt=True)
            # New Transformers versions may return a BatchEncoding instead of IDs.
            full=full['input_ids'] if isinstance(full,dict) or hasattr(full,'keys') else full
            prompt=prompt['input_ids'] if isinstance(prompt,dict) or hasattr(prompt,'keys') else prompt
            lengths.append(len(full))
            if len(full)>max_length: errors.append(f'{split}:{index}: {len(full)} tokens exceeds {max_length}')
            if len(prompt)>=len(full): errors.append(f'{split}:{index}: no completion tokens')
            if row['task'] in ['routing','evidence']: json.loads(messages[-1]['content'])
    if errors: raise ValueError('\n'.join(errors))
    return {'examples':len(lengths),'max_tokens':max(lengths),'mean_tokens':sum(lengths)/len(lengths),'valid':True}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('training/data'))
    p.add_argument('--model',default='training/base_model');p.add_argument('--max-length',type=int,default=1536)
    args=p.parse_args()
    from transformers import AutoTokenizer
    print(json.dumps(validate(args.data,AutoTokenizer.from_pretrained(args.model),args.max_length),indent=2))
