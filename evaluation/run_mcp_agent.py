"""Local-model generalization checks over synthetic Jira MCP responses.

Real Ollama inference; transport/data fixtures only. No question-specific routing.
Run: .venv/bin/python -m evaluation.run_mcp_agent --model qwen3.5:9b
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
from jsonschema import validate
from mcp.types import Tool
from main.src.integrations.mcp_agent import run
from main.src.integrations.mcp_client import jira_identifiers_supported
from main.src.tools.llm import Client

ROOT = Path(__file__).resolve().parents[1]
CONFIG = {'label': 'Synthetic Jira fixture', 'context': {'site_url': 'https://fixture.atlassian.net', 'project_key': 'LAB'}}
ACCOUNT = 'synthetic-account-48'
ISSUE = {'key': 'LAB-73', 'fields': {'summary': 'Build checkout API', 'status': {'name': 'In Progress'},
         'assignee': {'displayName': 'Taylor Example', 'accountId': ACCOUNT}, 'duedate': '2026-11-19'}}
SCHEMAS = {
    'getAccessibleAtlassianResources': ({}, [], 'List accessible sites and their cloudId identifiers.'),
    'getJiraCurrentUser': ({'cloudId': {'type': 'string'}}, ['cloudId'], 'Get current authenticated Jira account with displayName/accountId.'),
    'getJiraIssue': ({'cloudId': {'type': 'string'}, 'issueIdOrKey': {'type': 'string'}, 'view': {'type': 'string'}, 'fields': {'type': 'array', 'items': {'type': 'string'}}}, ['cloudId','issueIdOrKey'], 'Read current issue details. Use full view or explicit fields for due date; this is not changelog history.'),
    'searchJiraIssuesUsingJql': ({'cloudId': {'type': 'string'}, 'jql': {'type': 'string'}, 'maxResults': {'type': 'integer'}, 'fields': {'type': 'array','items': {'type': 'string'}}, 'view': {'type': 'string'}, 'nextPageToken': {'type': 'string'}}, ['cloudId','jql'], 'Search issues by JQL. Filter assignee/accountId, project and statusCategory. nextPageToken only from prior page.'),
    'listJiraBoards': ({'cloudId': {'type': 'string'}, 'projectKeyOrId': {'type': 'string'}}, ['cloudId'], 'Discover project boards and their numeric IDs.'),
    'listJiraBoardSprints': ({'cloudId': {'type': 'string'}, 'boardId': {'type': 'integer'}, 'state': {'type': 'string'}}, ['cloudId','boardId'], 'List sprints for a known board. Filter state active/future/closed.'),
    'listJiraIssueChangelogs': ({'cloudId': {'type': 'string'}, 'issueIdOrKey': {'type': 'string'}, 'startAt': {'type': 'integer'}, 'maxResults': {'type': 'integer'}}, ['cloudId','issueIdOrKey'], 'Read issue field-change history/changelog oldest first. Paginate using startAt and total; current details cannot answer history.'),
}
TOOLS = [Tool(name=name, description=description, input_schema={'type':'object','properties':properties,'required':required,'additionalProperties':False})
         for name,(properties,required,description) in SCHEMAS.items()]


class Fixture:
    def __init__(self): self.calls = []
    async def execute(self, name, args):
        tool = next(tool for tool in TOOLS if tool.name == name)
        validate(args, tool.input_schema)
        self.calls.append((name,args))
        error = False
        if 'cloudId' in args and args['cloudId'] != 'fixture-cloud':
            error, data = True, {'error': True, 'message': 'Invalid cloudId'}
        elif name == 'getAccessibleAtlassianResources':
            data = {'resources': [{'url': CONFIG['context']['site_url'], 'cloudId': 'fixture-cloud'}]}
        elif name == 'getJiraCurrentUser': data = {'accountId': ACCOUNT, 'displayName':'Taylor Example'}
        elif name == 'getJiraIssue': data = ISSUE if args['issueIdOrKey']=='LAB-73' else {'error':True,'message':'Issue not found'}
        elif name == 'searchJiraIssuesUsingJql':
            if 'assignee' not in args['jql'] and 'LAB-73' not in args['jql']:
                error, data = True, {'error': True, 'message': 'Narrow the query by assignee or issue key.'}
            else: data = {'issues':[ISSUE], 'isLast':True}
        elif name == 'listJiraBoards': data = {'values':[{'id':37,'name':'Lab engineering','type':'scrum'}], 'isLast':True}
        elif name == 'listJiraBoardSprints':
            data = {'values':[{'id':504,'name':'Checkout Sprint 6','state':'active','startDate':'2026-11-02','endDate':'2026-11-16'}], 'isLast':True}
            if args['boardId'] !=37: error,data=True,{'error':True,'message':'Discover the real board ID'}
        else:
            start=args.get('startAt',0)
            change={'id':str(start),'created':'2026-11-03T12:00:00Z','author':{'displayName':'Taylor Example'},'items':[{'field':'status','fromString':'To Do','toString':'In Progress'}]}
            if start: change['items']=[{'field':'duedate','fromString':None,'toString':'2026-11-19'}]
            data={'values':[change],'startAt':start,'maxResults':1,'total':2,'isLast':start>=1}
        return {'tool':name,'arguments':args,'is_error':error or isinstance(data,dict) and bool(data.get('error')),'content':{'data':data}}


CASES = [
    ('deadline','Could you check the deadline for LAB-73?', {'getJiraIssue'}, ['2026','19']),
    ('history_typo','What is the hostory of LAB-73?', {'listJiraIssueChangelogs'}, ['In Progress','19','2026']),
    ('history_paraphrase','Walk me through what changed on LAB-73 over time.', {'listJiraIssueChangelogs'}, ['In Progress','19','2026']),
    ('sprint','Which iteration is running for LAB right now, and when does it finish?', {'listJiraBoards','listJiraBoardSprints'}, ['Checkout Sprint 6','16']),
    ('assigned','What am I busy with in LAB, and what deadlines are recorded?', {'getJiraCurrentUser','searchJiraIssuesUsingJql'}, ['Build checkout API','19']),
    ('followup','Who owns it?', {'getJiraIssue'}, ['Taylor Example']),
]


async def evaluate(model):
    os.environ['JENNA_MCP_MODEL']=model
    results=[]
    for label,question,required,fragments in CASES:
        fixture=Fixture()
        history=[{'role':'user','content':'Tell me about LAB-73'},{'role':'assistant','content':'LAB-73 is the checkout API issue.'}] if label=='followup' else None
        try:
            result=await run(question,CONFIG,'jira',TOOLS,fixture.execute,Client(timeout=180),jira_identifiers_supported,history)
            reached={name for name,_ in fixture.calls}
            paginated = not label.startswith('history') or any(name=='listJiraIssueChangelogs' and args.get('startAt',0)>0 for name,args in fixture.calls)
            passed=required<=reached and paginated and all(fragment.casefold() in result['answer'].casefold() for fragment in fragments) and result['status']=='answered'
            results.append({'case':label,'passed':passed,'question':question,'answer':result['answer'],'status':result['status'],
                            'metrics':result['metrics'],'tools':[name for name,_ in fixture.calls], 'evidence': result['mcp_evidence']})
        except Exception as error:
            results.append({'case':label,'passed':False,'error':type(error).__name__})
        print(label, results[-1]['passed'], flush=True)
    report={'model':model,'passed':sum(r['passed'] for r in results),'total':len(results),'results':results,
            'scope':'Real local inference, synthetic MCP responses. Development generalization checks, not an independent benchmark.'}
    output=ROOT/'reports'/('mcp-agent-'+model.replace(':','-').replace('/','-')+'.json')
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(output,flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--model',default='qwen3.5:9b');args=p.parse_args()
    asyncio.run(evaluate(args.model))


if __name__=='__main__': main()
