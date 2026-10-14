"""Fuse local adapters, convert to compatible GGUF, optionally register in Ollama."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CONVERTER_REVISION='8bb3cf0d216a5ae48360179f2931daf284be4d01'


def run(args):
    subprocess.run(args,cwd=ROOT,check=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--skip-fuse',action='store_true')
    p.add_argument('--register',action='store_true');args=p.parse_args()
    if not args.skip_fuse:
        run([str(ROOT/'.venv-training/bin/mlx_lm.fuse'),'--model','training/base_model',
             '--adapter-path','training/adapters','--save-path','training/fused_model','--dequantize'])
    repo=ROOT/'training/vendor/llama.cpp'
    if not repo.exists():
        run(['git','clone','--depth','1','--filter=blob:none','--sparse',
             'https://github.com/ggml-org/llama.cpp.git',str(repo)])
        run(['git','-C',str(repo),'fetch','--depth','1','origin',CONVERTER_REVISION])
        run(['git','-C',str(repo),'checkout',CONVERTER_REVISION])
        run(['git','-C',str(repo),'sparse-checkout','set','conversion','gguf-py'])
    revision=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    if revision!=CONVERTER_REVISION:
        raise SystemExit('Converter checkout revision differs; use the documented pinned revision.')
    run([str(ROOT/'.venv/bin/python'),str(repo/'convert_hf_to_gguf.py'),'training/fused_model',
         '--outtype','q8_0','--outfile','training/jenna-finetuned-q8.gguf'])
    if args.register:
        run(['ollama','create','jenna-finetuned:latest','-f','training/Modelfile'])
    (ROOT/'training/export_manifest.json').write_text(json.dumps({
        'converter_revision':revision,'format':'GGUF Q8_0','ollama_model':'jenna-finetuned:latest',
        'registered':args.register,'private_weights':True},indent=2))


if __name__=='__main__':main()
