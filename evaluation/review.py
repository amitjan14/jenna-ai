"""Export human review forms and compare human labels to automatic grades."""
import argparse,csv,json
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('report',type=Path);p.add_argument('--labels',type=Path);p.add_argument('--output',type=Path,default=Path('reports/human-review.csv'));args=p.parse_args()
    report=json.loads(args.report.read_text())
    if not args.labels:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open('w',newline='') as output:
            writer=csv.DictWriter(output,fieldnames=['id','answer','automatic_pass','correct','supported','complete','appropriate_abstention','notes']);writer.writeheader()
            for row in report['results']:writer.writerow({'id':row['id'],'answer':row.get('answer',''),'automatic_pass':row['passed']})
    else:
        labels={row['id']:row for row in csv.DictReader(args.labels.open())};compared=[]
        for row in report['results']:
            label=labels.get(row['id'])
            if not label or any(label.get(key) not in {'0','1'} for key in ['correct','supported','complete','appropriate_abstention']):continue
            human=all(label[key]=='1' for key in ['correct','supported','complete','appropriate_abstention'])
            compared.append(human==row['passed'])
        print(json.dumps({'reviewed':len(compared),'agreement':sum(compared)/len(compared) if compared else None,'limitations':'Agreement is not accuracy; human labels should be independently reviewed.'}))


if __name__=='__main__':main()
