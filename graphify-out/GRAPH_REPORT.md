# Graph Report - jenna-ai  (2026-10-18)

## Corpus Check
- 117 files · ~80,586 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 2, .example 1, .jsonl 1)

## Summary
- 903 nodes · 2770 edges · 66 communities (28 shown, 38 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 208 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `c7f8641e`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- assistant_service.py
- run
- schemas.py
- json
- pathlib
- argparse
- instrument_request
- jira_workflow.py
- OutboundTests
- chat_memory.py
- JobManager
- build_server
- RefactorContracts
- test_engineering.py
- integrations/mcp_client.py
- llm.py
- test_core.py
- app.py
- voice.py
- mcp_auth.py
- MCP Protocol Tests
- prepare_data.py
- LoginCallback
- Evidence Validation Tests
- Shared Client Tests
- tracing.py
- Table Relation Tests
- Auto Search Behavior Tests
- runtime.py
- event
- FileTokenStorage
- Web Evidence Recovery Tests
- Upload Deletion Tests
- ConversationTests
- Jenna AI
- generalization.py
- ask_legacy
- Offline Evaluation Module
- Engineering Runtime Controls
- CoreTests
- jenna_personality.md
- AGENTS.md
- datasets/README.md
- run_mcp_question

## God Nodes (most connected - your core abstractions)
1. `run_assistant()` - 52 edges
2. `get_client()` - 45 edges
3. `run()` - 40 edges
4. `Role` - 40 edges
5. `ResultStatus` - 38 edges
6. `load_prompt()` - 34 edges
7. `PromptName` - 34 edges
8. `run_agent()` - 31 edges
9. `plan_request()` - 25 edges
10. `build_server()` - 25 edges

## Surprising Connections (you probably didn't know these)
- `Shared constants and patterns` --references--> `load_prompt()`  [INFERRED]
  README.md → main/src/utils/common_utils.py
- `generate()` --calls--> `validate()`  [INFERRED]
  main/src/integrations/mcp_client.py → training/validate_data.py
- `experiment()` --indirect_call--> `manifest()`  [INFERRED]
  evaluation/generalization.py → main/src/engineering/release.py
- `experiment()` --indirect_call--> `jira_identifiers_supported()`  [INFERRED]
  evaluation/generalization.py → main/src/integrations/mcp_client.py
- `main()` --calls--> `generate_document_answer()`  [EXTRACTED]
  evaluation/run_web_evidence.py → main/src/rag/rag_service.py

## Import Cycles
- None detected.

## Communities (66 total, 38 thin omitted)

### Community 0 - "assistant_service.py"
Cohesion: 0.06
Nodes (77): ast, jsonschema, clarification_selection(), decide_action(), Resolve an exact selection from 'Do you mean X or Y?'., resolve_followup(), run_agent(), search_and_answer() (+69 more)

### Community 1 - "run"
Cohesion: 0.08
Nodes (32): Scenario, benchmark(), request(), main(), Explicit cold-model and warmed-model latency measurements with local inference., main(), remote(), Actual local-model intent/typo checks, with isolated document and MCP fixtures. (+24 more)

### Community 2 - "schemas.py"
Cohesion: 0.12
Nodes (23): BaseModel, fastapi, fastapi_responses, cancel(), health(), job(), job_events(), Loopback REST API for Jenna jobs, traces, and readiness. (+15 more)

### Community 3 - "json"
Cohesion: 0.06
Nodes (63): chromadb, enum, main(), pdf(), Isolated RAG ablations: chunking, dense/hybrid retrieval, and reranking., worker(), main(), Evaluate the application's actual Chroma retrieval and reranker separately. (+55 more)

### Community 4 - "pathlib"
Cohesion: 0.09
Nodes (27): asyncio, Sequential actual-model dialogue development evaluation, isolated from personal…, main(), Real-model web-evidence regression; Tavily transport alone is mocked., main(), A minimal MCP client that connects to Jenna via stdio or local HTTP., use_session(), huggingface_hub (+19 more)

### Community 5 - "argparse"
Cohesion: 0.08
Nodes (27): argparse, contextlib, csv, main(), make_pdf(), Actual PDF ingestion and local-app evaluation on new documents, tables, and OCR., Export human review forms and compare human labels to automatic grades., assess() (+19 more)

### Community 6 - "instrument_request"
Cohesion: 0.23
Nodes (6): instrument_request(), execute(), measured(), AssistantTests, Model, planned()

### Community 7 - "jira_workflow.py"
Cohesion: 0.10
Nodes (21): active_sprint_request(), active_sprints(), read(), assigned_work(), read(), cell(), configured_cloud(), due_label() (+13 more)

### Community 8 - "OutboundTests"
Cohesion: 0.12
Nodes (9): Model, OutboundTests, connection(), connection(), plan(), Session, HTTPIntegrationTests, client() (+1 more)

### Community 9 - "chat_memory.py"
Cohesion: 0.18
Nodes (21): datetime, clear_chat_history(), delete_chat(), load_document_pdf(), load_document_records(), save_document(), database(), delete() (+13 more)

### Community 10 - "JobManager"
Cohesion: 0.18
Nodes (4): JobManager, handler(), APITests, handler()

### Community 11 - "build_server"
Cohesion: 0.11
Nodes (20): build_server(), ask_jenna(), backend(), calculate(), documents_data(), documents_resource(), forget_note(), list_chats() (+12 more)

### Community 13 - "test_engineering.py"
Cohesion: 0.15
Nodes (6): copy, Small TTL cache for stable read metadata, scoped to connection credentials., TTLCache, layout_pages(), EngineeringTests, threading

### Community 14 - "integrations/mcp_client.py"
Cohesion: 0.24
Nodes (17): credential_key(), oauth_provider(), token_storage(), ask(), catalog(), connect(), discover(), load_servers() (+9 more)

### Community 15 - "llm.py"
Cohesion: 0.12
Nodes (11): atexit, checkpoint(), Client, close_clients(), Measured Ollama client shared by routing and evidence selection., Administrative generation, used to unload models in benchmarks., Close pooled transports at process shutdown or explicit service teardown., Collect token deltas while publishing bounded local job/UI progress. (+3 more)

### Community 16 - "test_core.py"
Cohesion: 0.19
Nodes (10): memory_request(), forget_note(), list_notes(), note_details(), recall_note(), remember_note(), normalize_key(), AppSmokeTests (+2 more)

### Community 17 - "app.py"
Cohesion: 0.18
Nodes (17): fragment, render_pending_request(), create_chat(), list_chats(), load_messages(), save_message(), delete_document(), Remove the saved PDF and index; restore index if SQLite deletion fails. (+9 more)

### Community 18 - "voice.py"
Cohesion: 0.11
Nodes (14): faster_whisper, functools, io, kokoro, get_speech_pipeline(), get_transcriber(), prepare_speech_text(), synthesize_speech() (+6 more)

### Community 19 - "mcp_auth.py"
Cohesion: 0.17
Nodes (10): http_server, httpx2, PersistentOAuthProvider, SDK OAuth storage and an interactive loopback login callback., Restore SDK refresh prerequisites that are otherwise process-local., mcp_client_auth, mcp_client_auth_oauth2, OAuthClientProvider (+2 more)

### Community 21 - "prepare_data.py"
Cohesion: 0.21
Nodes (15): collections, gc, random, statistics, main(), Compare the same MLX base weights with and without local adapters., score(), encode() (+7 more)

### Community 25 - "tracing.py"
Cohesion: 0.15
Nodes (15): concurrent_futures, contextvars, Single-worker local request queue with progress and cooperative cancellation., connection(), db_path(), list_traces(), Local, content-minimized request traces. No prompts or tool outputs are stored., read_trace() (+7 more)

### Community 26 - "Table Relation Tests"
Cohesion: 0.33
Nodes (5): normalize(), Check short table values against their labels without model knowledge., table_relation_error(), table_field_pattern(), TableRelationTests

### Community 28 - "runtime.py"
Cohesion: 0.17
Nodes (9): dataclasses, main(), turn(), Control, DeadlineExceeded, RuntimeError, Cooperative cancellation, deadlines, and read-only retry controls., RequestCancelled (+1 more)

### Community 29 - "event"
Cohesion: 0.31
Nodes (6): Retry transient transport failures only; caller must enforce read-only policy., retry_read(), event(), execute(), RetryTests, read()

### Community 34 - "Jenna AI"
Cohesion: 0.14
Nodes (13): Automatic intent and sources, Conversation and follow-ups, Direct MCP integrations, Engineering tools, Evaluate the current application, Jenna AI, Local fine-tuning, Numerical word problems and supplied code (+5 more)

### Community 35 - "generalization.py"
Cohesion: 0.48
Nodes (6): assess(), experiment(), load_dataset(), main(), Versioned, split-aware local-agent experiments over synthetic MCP fixtures., hashlib

### Community 36 - "ask_legacy"
Cohesion: 0.33
Nodes (7): answer_evidence(), ask_legacy(), execute_jira(), generate(), call_read_tool(), compact_evidence(), Keep relevant paragraphs within the small local model's context window.

### Community 40 - "jenna_personality.md"
Cohesion: 0.40
Nodes (4): Behavior, Document Handling & Constraints, Personality, Role & Identity

## Knowledge Gaps
- **17 isolated node(s):** `graphify`, `Run`, `Use`, `Evaluate the current application`, `Local fine-tuning` (+12 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 271 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **38 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `load_prompt()` connect `assistant_service.py` to `run`, `Jenna AI`, `json`, `ask_legacy`, `pathlib`, `build_server`, `RefactorContracts`, `integrations/mcp_client.py`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._
- **Why does `run_assistant()` connect `assistant_service.py` to `run`, `schemas.py`, `json`, `pathlib`, `argparse`, `instrument_request`, `JobManager`, `integrations/mcp_client.py`, `llm.py`, `test_core.py`, `run_mcp_question`, `tracing.py`, `runtime.py`, `event`?**
  _High betweenness centrality (0.041) - this node is a cross-community bridge._
- **Why does `run()` connect `run` to `assistant_service.py`, `json`, `generalization.py`, `integrations/mcp_client.py`, `llm.py`, `tracing.py`, `event`?**
  _High betweenness centrality (0.036) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `run_assistant()` (e.g. with `AnswerKind` and `Connection`) actually correct?**
  _`run_assistant()` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `run()` (e.g. with `ExecutionStatus` and `PromptName`) actually correct?**
  _`run()` has 5 INFERRED edges - model-reasoned connections that need verification._
- **What connects `graphify`, `Run`, `Use` to the rest of the system?**
  _17 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `assistant_service.py` be split into smaller, more focused modules?**
  _Cohesion score 0.058797524314765696 - nodes in this community are weakly interconnected._