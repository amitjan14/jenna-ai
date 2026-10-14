"""Regression contracts for centralized domains, prompts and literal regex builders."""
import ast
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch
from jsonschema import validate, ValidationError
from pydantic import ValidationError as ModelValidationError
from main.src.utils import regex_constants as rx
from main.src.utils.enums import SearchMode, Intent, Role, PromptName

ROOT=Path(__file__).resolve().parents[2]


class RefactorContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A wrong repository root must fail, rather than silently scan zero files.
        if not (ROOT/'main/src').is_dir() or not (ROOT/'main/instructions').is_dir():
            raise AssertionError(f'Architecture checks cannot find project sources under {ROOT}')

    def test_moved_registry_loads_without_current_directory_dependency(self):
        from main.src.integrations.mcp_client import DEFAULT_CONFIG, load_servers
        self.assertTrue(DEFAULT_CONFIG.is_absolute())
        self.assertEqual(DEFAULT_CONFIG, ROOT/'main/mcp/servers.json')
        self.assertTrue(load_servers())
        for path in (ROOT/'main/mcp/clients').glob('*.json'):
            config=json.loads(path.read_text())
            for server in config.get('servers',config.get('mcpServers',{})).values():
                for argument in server.get('args',[]):
                    if argument.endswith('.py'):
                        # Templates contain machine-specific paths; verify the
                        # repository-relative target without requiring that machine.
                        relative=argument.split('/jenna-ai/',1)[-1]
                        self.assertTrue((ROOT/relative).is_file(), path)

    def test_release_fingerprint_includes_moved_registry(self):
        from main.src.engineering.release import manifest, sha
        with patch('main.src.engineering.release.ollama.Client') as client:
            client.return_value.list.return_value.models=[]
            files=manifest()['files']
        self.assertEqual(files['main/mcp/servers.json'],sha(ROOT/'main/mcp/servers.json'))
        self.assertNotIn('mcp/servers.json',files)

    def test_wire_contracts_accept_existing_strings_and_reject_unknown_modes(self):
        from main.src.tools.api import Ask
        from main.src.utils.schemas import ROUTE_SCHEMA,assistant_schema
        body=Ask.model_validate({'question':'hello','mode':'Documents','history':[{'role':'user','content':'hello'}]})
        encoded=json.loads(body.model_dump_json())
        self.assertEqual(encoded['mode'],'Documents');self.assertEqual(encoded['history'][0]['role'],'user')
        self.assertEqual(json.loads(json.dumps({'mode':SearchMode.AUTO,'intent':Intent.CHAT,'role':Role.ASSISTANT})),
                         {'mode':'Auto','intent':'chat','role':'assistant'})
        with self.assertRaises(ModelValidationError):Ask.model_validate({'question':'hello','mode':'unknown'})
        validate({'action':'search_documents','expression':''},ROUTE_SCHEMA)
        with self.assertRaises(ValidationError):validate({'action':'forget_note','expression':''},ROUTE_SCHEMA)
        self.assertEqual(assistant_schema(['local'])['properties']['mode']['enum'],[m.value for m in SearchMode])

    def test_dynamic_regex_values_are_literals_and_preserve_identifier_boundaries(self):
        self.assertEqual(re.findall(rx.vector_pattern('A+'),'A+ = [1, 2]'),['[1, 2]'])
        self.assertEqual(re.findall(rx.vector_pattern('A+'),'AAAA = [1, 2]'),[])
        self.assertIsNone(re.search(rx.exact_anchor_pattern('OPS-42'),'OPS-420'))
        self.assertIsNone(re.search(rx.identifier_pattern('OPS-42'),'OTHER-OPS-42'))
        self.assertIsNotNone(re.search(rx.typed_id_pattern('boardId','12'),'board id: 12',re.I))
        self.assertIsNone(re.search(rx.typed_id_pattern('boardId','12'),'board id: 123',re.I))

    def test_runtime_regex_literals_are_defined_only_in_regex_constants(self):
        functions={'compile','search','match','fullmatch','findall','finditer','sub','split'}
        violations=[]
        for path in (ROOT/'main/src').rglob('*.py'):
            if path.name=='regex_constants.py':continue
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='re' and node.func.attr in functions:
                    if isinstance(node.args[0],(ast.Constant,ast.JoinedStr,ast.BinOp)):
                        violations.append(f'{path}:{node.lineno}')
                if isinstance(node,ast.keyword) and node.arg in {'pattern','split_pattern'} and isinstance(node.value,ast.Constant):
                    violations.append(f'{path}:{node.lineno}')
        self.assertEqual(violations,[])

    def test_multi_query_prompt_uses_requested_question_and_count(self):
        from main.src.rag import rag_service as rag
        response={'message':{'content':json.dumps({'queries':['leave allowance','annual leave days']})}}
        with patch.object(rag.ollama_client,'chat',return_value=response) as chat:
            queries, seconds=rag.generate_multi_queries('What is the annual leave allowance?',num_queries=2)
            self.assertEqual(queries,['What is the annual leave allowance?','leave allowance','annual leave days'])
            self.assertGreaterEqual(seconds,0)
        request=chat.call_args.kwargs
        self.assertIn('Generate 2 alternative',request['messages'][0]['content'])
        self.assertIn('What is the annual leave allowance?',request['messages'][0]['content'])
        self.assertEqual(request['format']['properties']['queries']['maxItems'],2)

    def test_all_extracted_prompts_load_without_working_directory_dependency(self):
        from main.src.utils.common_utils import load_prompt
        for prompt in PromptName:
            kwargs={'question':'test question','num_queries':2} if prompt==PromptName.MULTI_QUERIES else {}
            self.assertTrue(load_prompt(prompt,**kwargs).strip())

    def test_owned_schemas_and_api_types_are_centralized(self):
        violations=[]
        for path in (ROOT/'main/src').rglob('*.py'):
            if path.name=='schemas.py':continue
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node,ast.Dict):
                    keys={k.value for k in node.keys if isinstance(k,ast.Constant)}
                    if {'type','properties'}<=keys:violations.append(f'{path}:{node.lineno}')
                if isinstance(node,ast.ClassDef) and any(isinstance(base,ast.Name) and base.id=='BaseModel' for base in node.bases):
                    violations.append(f'{path}:{node.lineno}')
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='Field':
                    violations.append(f'{path}:{node.lineno}')
        self.assertEqual(violations,[])

    def test_instruction_split_and_static_client_content_locations(self):
        from main.src.utils import instructions
        for name,value in vars(instructions).items():
            if name.isupper() and isinstance(value,str):
                self.assertLessEqual(len(value.splitlines()),3,name)
        for prompt in PromptName:
            path=ROOT/'main/instructions'/f'{prompt}.md'
            if prompt in instructions.SHORT_PROMPTS:
                self.assertFalse(path.exists())
            else:
                self.assertGreater(len(path.read_text().splitlines()),3,prompt)
        violations=[]
        for path in (ROOT/'main/src').rglob('*.py'):
            if path.name=='instructions.py':continue
            for node in ast.walk(ast.parse(path.read_text())):
                if not isinstance(node,ast.Dict):continue
                for key,value in zip(node.keys,node.values):
                    if isinstance(key,ast.Constant) and key.value=='content' and isinstance(value,ast.Constant) and isinstance(value.value,str) and value.value:
                        violations.append(f'{path}:{node.lineno}')
        self.assertEqual(violations,[])

    def test_schema_builders_preserve_external_constraints_and_do_not_mutate_base(self):
        from main.src.utils.schemas import MCP_PLAN_SCHEMA,mcp_selection_schema,mcp_tool_definition,DISCOVER_TOOLS_SCHEMA
        before=json.dumps(MCP_PLAN_SCHEMA)
        one=mcp_selection_schema(['first']);two=mcp_selection_schema(['second'])
        self.assertEqual(one['properties']['tool_name']['enum'],['','first'])
        self.assertEqual(two['properties']['tool_name']['enum'],['','second'])
        self.assertEqual(json.dumps(MCP_PLAN_SCHEMA),before)
        external={'type':'object','properties':{'id':{'type':'integer','minimum':1}},'required':['id']}
        wrapped=mcp_tool_definition('read_item','Read an item',external)
        self.assertIs(wrapped['function']['parameters'],external)
        with self.assertRaises(ValidationError):validate({'query':4},DISCOVER_TOOLS_SCHEMA)


if __name__=='__main__':unittest.main()
