# Graph Report - jenna-ai  (2026-10-24)

## Corpus Check
- 133 files · ~118,634 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 2, .example 1, .jsonl 1)

## Summary
- 1119 nodes · 3430 edges · 74 communities (37 shown, 37 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 237 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `16df07b7`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- run_assistant
- test_mcp.py
- jira_identifiers_supported
- IndexRollbackTests
- chat_memory.py
- test_engineering.py
- voice.py
- jira_workflow.py
- FileTokenStorage
- assistant_service.py
- api.py
- build_server
- run_visual_documents.py
- sample_test.py
- run
- mcp_tool_definition
- json
- runtime.py
- app.py
- generalization.py
- MCP Protocol Tests
- prepare_data.py
- test_mcp_client.py
- EvidenceTests
- Shared Client Tests
- run_auto_documents.py
- integrations/mcp_client.py
- export.py
- memory_service.py
- RefactorContracts
- VoiceTests
- run_agent.py
- Jenna AI
- AutoSearchTests
- Offline Evaluation Module
- Engineering Runtime Controls
- test_core.py
- jenna_personality.md
- test_pdf_visual.py
- AGENTS.md
- datasets/README.md
- WebTests
- document_store.py
- pathlib
- test_conversation.py
- mcp_auth.py
- LoginCallback
- ask_legacy
- event
- PersistentOAuthProvider
- .test_delete_clears_selection_and_explicit_reselection_can_upload_again

## God Nodes (most connected - your core abstractions)
1. `run_assistant()` - 58 edges
2. `timed_step()` - 56 edges
3. `get_client()` - 48 edges
4. `run()` - 44 edges
5. `Role` - 43 edges
6. `plan_request()` - 39 edges
7. `Model` - 39 edges
8. `ResultStatus` - 38 edges
9. `planned()` - 38 edges
10. `load_prompt()` - 37 edges

## Surprising Connections (you probably didn't know these)
- `Shared constants and patterns` --references--> `load_prompt()`  [INFERRED]
  README.md → main/src/utils/common_utils.py
- `experiment()` --indirect_call--> `manifest()`  [INFERRED]
  evaluation/generalization.py → main/src/engineering/release.py
- `experiment()` --indirect_call--> `jira_identifiers_supported()`  [INFERRED]
  evaluation/generalization.py → main/src/integrations/mcp_client.py
- `remote()` --indirect_call--> `jira_identifiers_supported()`  [INFERRED]
  evaluation/run_intent.py → main/src/integrations/mcp_client.py
- `plan_request()` --calls--> `validate()`  [INFERRED]
  main/src/agent/assistant_service.py → training/validate_data.py

## Import Cycles
- None detected.

## Communities (74 total, 37 thin omitted)

### Community 0 - "run_assistant"
Cohesion: 0.05
Nodes (18): needs_conversation_context(), matches_uploaded_document(), plan_request(), preserve_document_question(), A standalone source question is authoritative, not a model paraphrase., Resolve one literal filename/unique title; do not narrow comparisons., referenced_document_filter(), run_assistant() (+10 more)

### Community 1 - "test_mcp.py"
Cohesion: 0.19
Nodes (9): main(), A minimal MCP client that connects to Jenna via stdio or local HTTP., use_session(), mcp, mcp_client_stdio, mcp_client_streamable_http, socket, sys (+1 more)

### Community 2 - "jira_identifiers_supported"
Cohesion: 0.15
Nodes (12): benchmark(), request(), main(), evaluate(), Fixture, main(), jira_identifiers_supported(), collect() (+4 more)

### Community 4 - "chat_memory.py"
Cohesion: 0.24
Nodes (9): datetime, create_chat(), list_chats(), load_messages(), save_message(), insert(), Generic SQLite INSERT statement. :param table_name: Name of the target table.…, ChatRecencyTests (+1 more)

### Community 5 - "test_engineering.py"
Cohesion: 0.26
Nodes (12): main(), make_pdf(), Actual PDF ingestion and local-app evaluation on new documents, tables, and OCR., behavior_fingerprint_matches(), gate(), manifest(), Content-addressed manifests and measurable release gates., sha() (+4 more)

### Community 6 - "voice.py"
Cohesion: 0.21
Nodes (11): faster_whisper, functools, kokoro, get_speech_pipeline(), get_transcriber(), prepare_speech_text(), synthesize_speech(), transcribe_audio() (+3 more)

### Community 7 - "jira_workflow.py"
Cohesion: 0.09
Nodes (28): has_jira_intent(), A person's name alone does not establish a Jira lookup., active_sprint_request(), active_sprints(), outcome(), read(), assigned_work(), outcome() (+20 more)

### Community 8 - "FileTokenStorage"
Cohesion: 0.07
Nodes (11): FileTokenStorage, Model, OutboundTests, connection(), connection(), plan(), Session, HTTPIntegrationTests (+3 more)

### Community 9 - "assistant_service.py"
Cohesion: 0.06
Nodes (123): ast, atexit, BaseModel, chromadb, contextvars, enum, main(), inspect (+115 more)

### Community 10 - "api.py"
Cohesion: 0.06
Nodes (38): fastapi, fastapi_responses, connection(), db_path(), list_traces(), Measure inclusive and exclusive wall time without storing arguments., request_trace(), safe() (+30 more)

### Community 11 - "build_server"
Cohesion: 0.09
Nodes (28): importlib_metadata, doctor(), main(), Local service diagnostics and a terminal client for Jenna., add_arguments(), build_server(), ask_jenna(), backend() (+20 more)

### Community 12 - "run_visual_documents.py"
Cohesion: 0.26
Nodes (10): main(), pdf(), Isolated RAG ablations: chunking, dense/hybrid retrieval, and reranking., worker(), font(), main(), make_document(), raster() (+2 more)

### Community 13 - "sample_test.py"
Cohesion: 0.09
Nodes (15): bm25_search(), embed_batch(), safe_embed(), embed_chunks(), parallel_embed(), evaluate_retrieval(), filter_results(), get_embedding() (+7 more)

### Community 14 - "run"
Cohesion: 0.13
Nodes (16): due_date_facts(), visit(), prepare_due_date_read(), Request the actual field; compact/evidence views may omit it entirely., Expose field presence explicitly, preserving null versus omitted values., bounded(), message_dict(), pending_pages() (+8 more)

### Community 15 - "mcp_tool_definition"
Cohesion: 0.67
Nodes (4): rebuild_definitions(), discovery_tool_definition(), mcp_tool_definition(), Wrap a discovered schema without changing its server-provided constraints.

### Community 16 - "json"
Cohesion: 0.18
Nodes (11): argparse, asyncio, csv, Explicit cold-model and warmed-model latency measurements with local inference., Export human review forms and compare human labels to automatic grades., Actual local-model intent/typo checks, with isolated document and MCP fixtures., Local-model generalization checks over synthetic Jira MCP responses. Real…, json (+3 more)

### Community 17 - "runtime.py"
Cohesion: 0.06
Nodes (25): concurrent_futures, dataclasses, main(), turn(), natural_summary(), Synthesize a cited answer only after extractive evidence validation succeeds., JobManager, Single-worker local request queue with progress and cooperative cancellation. (+17 more)

### Community 18 - "app.py"
Cohesion: 0.33
Nodes (10): fragment, render_pending_request(), clear_active_chat(), delete_saved_chat(), display_passages(), display_retrieval_failure(), play_spoken_reply(), select_chat() (+2 more)

### Community 19 - "generalization.py"
Cohesion: 0.26
Nodes (9): copy, assess(), experiment(), load_dataset(), main(), Versioned, split-aware local-agent experiments over synthetic MCP fixtures., Scenario, main() (+1 more)

### Community 21 - "prepare_data.py"
Cohesion: 0.40
Nodes (10): collections, random, encode(), evidence_rules(), example(), prepare(), project_examples(), Build local multitask SFT data; source documents and chats never leave disk. (+2 more)

### Community 22 - "test_mcp_client.py"
Cohesion: 0.25
Nodes (5): Direct connections to external MCP servers., ConfigTests, Outbound MCP contracts, bounded planning, and credential storage., mcp_types, stat

### Community 25 - "run_auto_documents.py"
Cohesion: 0.27
Nodes (6): flow_checks(), main(), pdf_bytes(), Auto source-boundary and full-flow development benchmarks using isolated PDFs.…, AutoBenchmarkScoringTests, The benchmark must not reward crashes, refusals, or another person's resume.

### Community 26 - "integrations/mcp_client.py"
Cohesion: 0.34
Nodes (13): credential_key(), oauth_provider(), token_storage(), catalog(), connect(), discover(), load_servers(), main() (+5 more)

### Community 27 - "export.py"
Cohesion: 0.67
Nodes (3): main(), Fuse local adapters, convert to compatible GGUF, optionally register in Ollama., run()

### Community 28 - "memory_service.py"
Cohesion: 0.17
Nodes (12): load_document_pdf(), load_document_records(), save_document(), fetch_record(), fetch_records(), Generic database fetch query builder. :param table_name: Target table name.…, Generic database fetch query builder. :param table_name: Target table name.…, Generic SQLite UPSERT. Inserts a record, or updates the existing record when… (+4 more)

### Community 33 - "run_agent.py"
Cohesion: 0.19
Nodes (11): contextlib, assess(), main(), percentile(), Exercise the real app pipeline against an isolated, labeled synthetic corpus., Evaluate the application's actual Chroma retrieval and reranker separately., gc, statistics (+3 more)

### Community 34 - "Jenna AI"
Cohesion: 0.14
Nodes (13): Automatic intent and sources, Conversation and follow-ups, Direct MCP integrations, Engineering tools, Evaluate the current application, Jenna AI, Local fine-tuning, Numerical word problems and supplied code (+5 more)

### Community 39 - "test_core.py"
Cohesion: 0.09
Nodes (10): normalize(), Check short table values against their labels without model knowledge., table_relation_error(), cosine_similarity(), table_field_pattern(), CoreTests, IngestionTests, RoutingTests (+2 more)

### Community 40 - "jenna_personality.md"
Cohesion: 0.40
Nodes (4): Behavior, Document Handling & Constraints, Personality, Role & Identity

### Community 42 - "test_pdf_visual.py"
Cohesion: 0.07
Nodes (10): For a uniquely named short image, read its transcription, not its label., visual_content_passage(), image_pdf(), PDF visual extraction and original-pixel verification contracts., VisualContentTests, VisualExtractionTests, VisualIndexTests, VisualVerificationTests (+2 more)

### Community 68 - "document_store.py"
Cohesion: 0.05
Nodes (37): main(), TTLCache, checkpoint(), Time library calls, which cannot be decorated at their definition., timed_call(), add_document(), delete_document(), _index_snapshot() (+29 more)

### Community 70 - "pathlib"
Cohesion: 0.14
Nodes (12): Sequential actual-model dialogue development evaluation, isolated from personal…, Real-model web-evidence regression; Tavily transport alone is mocked., huggingface_hub, io, Literal local web credential lookup without executing shell configuration., ClientArchitectureTests, Shared provider lifecycle and request isolation; no inference or network calls., pathlib (+4 more)

### Community 73 - "test_conversation.py"
Cohesion: 0.31
Nodes (9): load_state(), save_state(), clear_chat_history(), delete_chat(), database(), delete(), Generic SQLite UPDATE statement. :param table_name: Name of the target table.…, Generic SQLite DELETE statement. :param table_name: Name of the target table.… (+1 more)

### Community 76 - "mcp_auth.py"
Cohesion: 0.15
Nodes (13): main(), Development regression: local numerical planning and inline-code assistance. No…, hashlib, http_server, httpx2, Small TTL cache for stable read metadata, scoped to connection credentials., SDK OAuth storage and an interactive loopback login callback., mcp_client_auth (+5 more)

### Community 78 - "ask_legacy"
Cohesion: 0.24
Nodes (9): answer_evidence(), ask_legacy(), execute_jira(), generate(), call_read_tool(), compact_evidence(), Keep relevant paragraphs within the small local model's context window., mcp_selection_schema() (+1 more)

### Community 80 - "event"
Cohesion: 0.24
Nodes (9): Retry transient transport failures only; caller must enforce read-only policy., retry_read(), event(), ask(), execute(), Use one general local tool-calling agent for every MCP server/question., reject(), RetryTests (+1 more)

### Community 83 - "PersistentOAuthProvider"
Cohesion: 0.50
Nodes (3): PersistentOAuthProvider, Restore SDK refresh prerequisites that are otherwise process-local., OAuthClientProvider

## Knowledge Gaps
- **17 isolated node(s):** `graphify`, `Run`, `Use`, `Evaluate the current application`, `Local fine-tuning` (+12 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 328 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **37 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `build_server()` connect `build_server` to `assistant_service.py`, `test_mcp.py`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **Why does `load_prompt()` connect `assistant_service.py` to `run_assistant`, `Jenna AI`, `build_server`, `run`, `ask_legacy`, `runtime.py`, `integrations/mcp_client.py`, `RefactorContracts`?**
  _High betweenness centrality (0.039) - this node is a cross-community bridge._
- **Why does `SharedClientTests` connect `Shared Client Tests` to `pathlib`?**
  _High betweenness centrality (0.035) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `run_assistant()` (e.g. with `AnswerKind` and `Connection`) actually correct?**
  _`run_assistant()` has 6 INFERRED edges - model-reasoned connections that need verification._
- **What connects `graphify`, `Run`, `Use` to the rest of the system?**
  _17 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `run_assistant` be split into smaller, more focused modules?**
  _Cohesion score 0.05417236662106703 - nodes in this community are weakly interconnected._
- **Should `jira_workflow.py` be split into smaller, more focused modules?**
  _Cohesion score 0.08673469387755102 - nodes in this community are weakly interconnected._