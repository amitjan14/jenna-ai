"""Download public weights at the revision used for the verified local run."""
from pathlib import Path
from huggingface_hub import snapshot_download

ROOT=Path(__file__).resolve().parents[1]
MODEL='mlx-community/Llama-3.2-3B-Instruct-4bit'
REVISION='7f0dc925e0d0afb0322d96f9255cfddf2ba5636e'

if __name__=='__main__':
    print(snapshot_download(MODEL,revision=REVISION,local_dir=ROOT/'training/base_model',
                            ignore_patterns=['*.md','.gitattributes']))
