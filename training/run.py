"""Reproducible local training entry point; validates before allocating a model."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--include-project-data',action='store_true')
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args()
    command=[sys.executable,str(ROOT/'training/prepare_data.py')]
    if args.include_project_data:command.append('--include-project-data')
    subprocess.run(command,cwd=ROOT,check=True)
    subprocess.run([sys.executable,str(ROOT/'training/validate_data.py')],cwd=ROOT,check=True)
    if not args.prepare_only:
        subprocess.run([str(Path(sys.executable).parent/'mlx_lm.lora'),'--config','training/train.yaml'],cwd=ROOT,check=True)


if __name__=='__main__':main()
