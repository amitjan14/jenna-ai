# Graph Report - jenna-ai  (2026-10-14)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 859 nodes · 2734 edges · 44 communities (24 shown, 20 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 207 edges (avg confidence: 0.92)
- Token cost: 1,878 input · 6,605 output

## Graph Freshness
- Built from commit: `6c1ae47b`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Agent Service Orchestration
- Local Agent Benchmarking
- Request Queue Management
- RAG Retrieval Experiments
- Performance Regression Testing
- PDF Ingestion Evaluation
- Arithmetic Conversation Tests
- Jira Workflow Integration
- Client Token Storage
- Chat Document Memory
- Job Control Management
- Backend API Endpoints
- Tool Calling Evidence
- Runtime Retry Logic
- MCP Client Discovery
- LLM Client Interface
- Note Memory MCP Server
- Session Document Management
- Speech Processing Pipeline
- OAuth Auth Server
- MCP Protocol Tests
- Synthetic Data Generation
- Login Callback Handler
- Evidence Validation Tests
- Shared Client Tests
- Local Training Export
- Table Relation Tests
- Auto Search Behavior Tests
- Runtime Error Handling
- Retry Logic Tests
- Web Search Response Tests
- Web Evidence Recovery Tests
- Upload Deletion Tests
- Voice Transcription Tests
- Model Weight Downloading
- PDF Ingestion Tests
- Query Routing Tests
- Offline Evaluation Module
- Engineering Runtime Controls
- External MCP Integrations
- Config Validation Tests

## God Nodes (most connected - your core abstractions)
1. `run_assistant()` - 52 edges
2. `get_client()` - 45 edges
3. `Role` - 40 edges
4. `run()` - 40 edges
5. `ResultStatus` - 38 edges
6. `PromptName` - 34 edges
7. `load_prompt()` - 33 edges
8. `run_agent()` - 31 edges
9. `build_server()` - 25 edges
10. `plan_request()` - 25 edges

## Surprising Connections (you probably didn't know these)
- `natural_summary()` --calls--> `validate()`  [INFERRED]
  main/src/agent/conversation.py → training/validate_data.py
- `verify_grounded()` --calls--> `validate()`  [INFERRED]
  main/src/agent/conversation.py → training/validate_data.py
- `main()` --calls--> `generate_document_answer()`  [EXTRACTED]
  evaluation/run_web_evidence.py → main/src/rag/rag_service.py
- `run_calculation()` --calls--> `validate()`  [INFERRED]
  main/src/tools/calculator.py → training/validate_data.py
- `experiment()` --indirect_call--> `manifest()`  [INFERRED]
  evaluation/generalization.py → main/src/engineering/release.py

## Import Cycles
- None detected.

## Communities (44 total, 20 thin omitted)

### Community 0 - "Agent Service Orchestration"
Cohesion: 0.07
Nodes (83): chromadb, jsonschema, logging, clarification_selection(), decide_action(), Resolve an exact selection from 'Do you mean X or Y?'., resolve_followup(), run_agent() (+75 more)

### Community 1 - "Local Agent Benchmarking"
Cohesion: 0.07
Nodes (38): assess(), experiment(), load_dataset(), main(), Versioned, split-aware local-agent experiments over synthetic MCP fixtures., Scenario, benchmark(), request() (+30 more)

### Community 2 - "Request Queue Management"
Cohesion: 0.08
Nodes (47): BaseModel, concurrent_futures, enum, fastapi, fastapi_responses, importlib_metadata, Single-worker local request queue with progress and cooperative cancellation., cancel() (+39 more)

### Community 3 - "RAG Retrieval Experiments"
Cohesion: 0.06
Nodes (40): collections, main(), pdf(), Isolated RAG ablations: chunking, dense/hybrid retrieval, and reranking., worker(), assess(), main(), percentile() (+32 more)

### Community 4 - "Performance Regression Testing"
Cohesion: 0.09
Nodes (34): argparse, ast, asyncio, contextlib, csv, Explicit cold-model and warmed-model latency measurements with local inference., Export human review forms and compare human labels to automatic grades., Development regression: local numerical planning and inline-code assistance. No… (+26 more)

### Community 5 - "PDF Ingestion Evaluation"
Cohesion: 0.08
Nodes (25): contextvars, main(), make_pdf(), Actual PDF ingestion and local-app evaluation on new documents, tables, and OCR., io, TTLCache, behavior_fingerprint_matches(), gate() (+17 more)

### Community 6 - "Arithmetic Conversation Tests"
Cohesion: 0.09
Nodes (9): main(), plan_request(), run_assistant(), verify(), ArithmeticFollowupTests, AssistantTests, Model, planned() (+1 more)

### Community 7 - "Jira Workflow Integration"
Cohesion: 0.10
Nodes (21): active_sprint_request(), active_sprints(), read(), assigned_work(), read(), cell(), configured_cloud(), due_label() (+13 more)

### Community 8 - "Client Token Storage"
Cohesion: 0.07
Nodes (11): FileTokenStorage, Model, OutboundTests, connection(), connection(), plan(), Session, HTTPIntegrationTests (+3 more)

### Community 9 - "Chat Document Memory"
Cohesion: 0.14
Nodes (23): datetime, load_state(), save_state(), clear_chat_history(), create_chat(), delete_chat(), load_messages(), save_message() (+15 more)

### Community 10 - "Job Control Management"
Cohesion: 0.08
Nodes (9): main(), turn(), JobManager, Control, ConversationTests, handler(), Model, APITests (+1 more)

### Community 11 - "Backend API Endpoints"
Cohesion: 0.11
Nodes (21): load_document_pdf(), build_server(), ask_jenna(), backend(), calculate(), documents_data(), documents_resource(), forget_note() (+13 more)

### Community 12 - "Tool Calling Evidence"
Cohesion: 0.12
Nodes (10): answer_evidence(), ask_legacy(), execute_jira(), generate(), call_read_tool(), compact_evidence(), Keep relevant paragraphs within the small local model's context window., mcp_selection_schema() (+2 more)

### Community 13 - "Runtime Retry Logic"
Cohesion: 0.18
Nodes (16): atexit, dataclasses, httpx2, checkpoint(), Cooperative cancellation, deadlines, and read-only retry controls., Retry transient transport failures only; caller must enforce read-only policy., retry_read(), event() (+8 more)

### Community 14 - "MCP Client Discovery"
Cohesion: 0.25
Nodes (15): copy, credential_key(), Small TTL cache for stable read metadata, scoped to connection credentials., oauth_provider(), token_storage(), catalog(), connect(), discover() (+7 more)

### Community 15 - "LLM Client Interface"
Cohesion: 0.16
Nodes (6): Client, Administrative generation, used to unload models in benchmarks., Collect token deltas while publishing bounded local job/UI progress., record_call(), inner(), outer()

### Community 16 - "Note Memory MCP Server"
Cohesion: 0.29
Nodes (9): memory_request(), forget_note(), list_notes(), note_details(), recall_note(), remember_note(), Jenna's standard MCP server: stdio or loopback Streamable HTTP., normalize_key() (+1 more)

### Community 17 - "Session Document Management"
Cohesion: 0.23
Nodes (14): fragment, hashlib, render_pending_request(), list_chats(), delete_document(), Remove the saved PDF and index; restore index if SQLite deletion fails., clear_active_chat(), delete_saved_chat() (+6 more)

### Community 18 - "Speech Processing Pipeline"
Cohesion: 0.21
Nodes (11): faster_whisper, functools, kokoro, get_speech_pipeline(), get_transcriber(), prepare_speech_text(), synthesize_speech(), transcribe_audio() (+3 more)

### Community 19 - "OAuth Auth Server"
Cohesion: 0.18
Nodes (9): http_server, PersistentOAuthProvider, SDK OAuth storage and an interactive loopback login callback., Restore SDK refresh prerequisites that are otherwise process-local., mcp_client_auth, mcp_client_auth_oauth2, OAuthClientProvider, urllib_parse (+1 more)

### Community 21 - "Synthetic Data Generation"
Cohesion: 0.47
Nodes (9): random, encode(), evidence_rules(), example(), prepare(), project_examples(), Build local multitask SFT data; source documents and chats never leave disk., route() (+1 more)

### Community 25 - "Local Training Export"
Cohesion: 0.29
Nodes (5): sys, main(), Fuse local adapters, convert to compatible GGUF, optionally register in Ollama., run(), Reproducible local training entry point; validates before allocating a model.

### Community 26 - "Table Relation Tests"
Cohesion: 0.33
Nodes (5): normalize(), Check short table values against their labels without model knowledge., table_relation_error(), table_field_pattern(), TableRelationTests

### Community 28 - "Runtime Error Handling"
Cohesion: 0.33
Nodes (6): DeadlineExceeded, RuntimeError, RequestCancelled, run_mcp_question(), control_error(), TimeoutError

## Knowledge Gaps
- **20 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `run_assistant()` connect `Arithmetic Conversation Tests` to `Agent Service Orchestration`, `Local Agent Benchmarking`, `Request Queue Management`, `RAG Retrieval Experiments`, `Performance Regression Testing`, `Chat Document Memory`, `Job Control Management`, `Runtime Retry Logic`, `MCP Client Discovery`, `Note Memory MCP Server`, `Runtime Error Handling`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Why does `run()` connect `Local Agent Benchmarking` to `Agent Service Orchestration`, `Request Queue Management`, `Performance Regression Testing`, `Arithmetic Conversation Tests`, `Tool Calling Evidence`, `Runtime Retry Logic`, `MCP Client Discovery`?**
  _High betweenness centrality (0.040) - this node is a cross-community bridge._
- **Why does `get_client()` connect `Agent Service Orchestration` to `Local Agent Benchmarking`, `Request Queue Management`, `RAG Retrieval Experiments`, `Performance Regression Testing`, `PDF Ingestion Evaluation`, `Arithmetic Conversation Tests`, `Tool Calling Evidence`, `Runtime Retry Logic`, `MCP Client Discovery`, `LLM Client Interface`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `run_assistant()` (e.g. with `AnswerKind` and `Connection`) actually correct?**
  _`run_assistant()` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 25 inferred relationships involving `Role` (e.g. with `clarification_selection()` and `decide_action()`) actually correct?**
  _`Role` has 25 INFERRED edges - model-reasoned connections that need verification._
- **Should `Agent Service Orchestration` be split into smaller, more focused modules?**
  _Cohesion score 0.07425742574257425 - nodes in this community are weakly interconnected._
- **Should `Local Agent Benchmarking` be split into smaller, more focused modules?**
  _Cohesion score 0.0701484895033282 - nodes in this community are weakly interconnected._