"""Local/CI validation entry point. Model quality gates require complete split reports."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from main.src.engineering.release import manifest,gate,sha


def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path);p.add_argument('--baseline',type=Path)
    p.add_argument('--min-success',type=float,default=.8);p.add_argument('--max-p95',type=float)
    p.add_argument('--pdf-report',type=Path)
    p.add_argument('--skip-tests',action='store_true');p.add_argument('--output',type=Path,default=ROOT/'reports/release-check.json');args=p.parse_args()
    if not 0<=args.min_success<=1:p.error('Invalid success threshold')
    checks={}
    commands=[('dataset',[sys.executable,'-m','evaluation.generalization','--validate-only']),
              ('compile',[sys.executable,'-m','compileall','-q','main/src','evaluation','scripts'])]
    if not args.skip_tests:commands.append(('tests',[sys.executable,'-m','unittest','discover','-s','main/tests','-v']))
    for name,cmd in commands:
        result=subprocess.run(cmd,cwd=ROOT);checks[name]=result.returncode==0
    if args.candidate:
        report=json.loads(args.candidate.read_text());baseline=json.loads(args.baseline.read_text()) if args.baseline else None
        quality=gate(report,baseline,args.min_success,args.max_p95)
        expected=18 if report['split']=='heldout' else 42
        quality['checks']['full_split']=report['summary']['total']==expected
        quality['passed']=all(quality['checks'].values());checks['quality']=quality['passed']
    else:quality={'status':'not_run','reason':'Supply a completed development or held-out model report'}
    if args.pdf_report:
        pdf=json.loads(args.pdf_report.read_text());s=pdf['summary'];expected=6 if pdf['split']=='heldout' else 14
        from main.src.engineering.release import behavior_fingerprint_matches
        checks['pdf_quality']=s.get('complete') and s['total']==expected and s['passed']/max(1,s['total'])>=args.min_success and pdf.get('dataset_sha256')==sha(ROOT/'evaluation/datasets/pdf_generalization.json') and behavior_fingerprint_matches(pdf.get('manifest',{}),manifest())
    payload={'passed':all(checks.values()),'checks':checks,'quality_gate':quality,'manifest':manifest()}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(payload,indent=2)+'\n')
    return 0 if payload['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
