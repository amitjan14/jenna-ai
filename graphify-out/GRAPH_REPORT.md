# Graph Report - jenna-ai  (2026-10-24)

## Corpus Check
- 135 files · ~119,476 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 2, .example 1, .jsonl 1)

## Summary
- 1136 nodes · 3479 edges · 85 communities (48 shown, 37 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 238 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `16df07b7`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- plan_request
- pathlib
- rag_service.py
- run_assistant
- create_chat
- test_engineering.py
- voice.py
- jira_workflow.py
- OutboundTests
- enums.py
- tracing.py
- mcp_server.py
- test_pdf_visual.py
- sample_test.py
- run
- web_tools.py
- json
- JobManager
- app.py
- run_calculation
- MCP Protocol Tests
- prepare_data.py
- api.py
- EvidenceTests
- Shared Client Tests
- run_auto_documents.py
- integrations/mcp_client.py
- document_store.py
- chat_memory.py
- search_utils.py
- agent_service.py
- FileTokenStorage
- VoiceTests
- test_conversation.py
- Jenna AI
- calculator.py
- AutoSearchTests
- Offline Evaluation Module
- Engineering Runtime Controls
- test_core.py
- jenna_personality.md
- VisualExtractionTests
- AGENTS.md
- datasets/README.md
- llm.py
- WebTests
- add_source_details
- timed_step
- EngineeringTests
- os
- timings.py
- visual_content_passage
- assistant_service.py
- mcp_auth.py
- LoginCallback
- cache.py
- table_relation_error
- retry_read
- record_call
- rag_experiments.py
- WebEvidenceRecoveryTests
- run_mcp_question

## God Nodes (most connected - your core abstractions)
1. `run_assistant()` - 59 edges
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
- `generate()` --calls--> `validate()`  [INFERRED]
  main/src/integrations/mcp_client.py → training/validate_data.py
- `experiment()` --indirect_call--> `manifest()`  [INFERRED]
  evaluation/generalization.py → main/src/engineering/release.py
- `plan_request()` --calls--> `validate()`  [INFERRED]
  main/src/agent/assistant_service.py → training/validate_data.py
- `run()` --calls--> `validate()`  [INFERRED]
  main/src/integrations/mcp_agent.py → training/validate_data.py

## Import Cycles
- None detected.

## Communities (85 total, 37 thin omitted)

### Community 0 - "plan_request"
Cohesion: 0.09
Nodes (10): matches_uploaded_document(), plan_request(), exact_anchor_pattern(), AssistantTests, inner(), outer(), Model, planned() (+2 more)

### Community 1 - "pathlib"
Cohesion: 0.16
Nodes (12): main(), A minimal MCP client that connects to Jenna via stdio or local HTTP., use_session(), huggingface_hub, mcp, mcp_client_stdio, mcp_client_streamable_http, pathlib (+4 more)

### Community 2 - "rag_service.py"
Cohesion: 0.15
Nodes (17): chromadb, logging, fit_messages(), Budgeted tool schemas and structured context compaction., select_tools(), summarize_history(), tokens(), Render requested source details from trusted retrieval metadata, not model… (+9 more)

### Community 3 - "run_assistant"
Cohesion: 0.17
Nodes (10): Resolve one literal filename/unique title; do not narrow comparisons., referenced_document_filter(), run_assistant(), parse_explicit_arithmetic(), Handle unambiguous arithmetic syntax without an LLM planning call., Continue a calculator result, recomputing its expression rather than guessing a…, resolve_arithmetic_followup(), document_reference_pattern() (+2 more)

### Community 4 - "create_chat"
Cohesion: 0.27
Nodes (6): fragment, render_pending_request(), create_chat(), load_messages(), save_message(), ChatRecencyTests

### Community 5 - "test_engineering.py"
Cohesion: 0.26
Nodes (12): main(), make_pdf(), Actual PDF ingestion and local-app evaluation on new documents, tables, and OCR., behavior_fingerprint_matches(), gate(), manifest(), Content-addressed manifests and measurable release gates., sha() (+4 more)

### Community 6 - "voice.py"
Cohesion: 0.24
Nodes (10): faster_whisper, kokoro, get_speech_pipeline(), get_transcriber(), prepare_speech_text(), synthesize_speech(), transcribe_audio(), numpy (+2 more)

### Community 7 - "jira_workflow.py"
Cohesion: 0.08
Nodes (33): datetime, has_jira_intent(), A person's name alone does not establish a Jira lookup., active_sprint_request(), active_sprints(), outcome(), read(), assigned_work() (+25 more)

### Community 8 - "OutboundTests"
Cohesion: 0.12
Nodes (9): Model, OutboundTests, connection(), connection(), plan(), Session, HTTPIntegrationTests, client() (+1 more)

### Community 9 - "enums.py"
Cohesion: 0.10
Nodes (26): ast, BaseModel, enum, preserve_document_question(), A standalone source question is authoritative, not a model paraphrase., rebuild_definitions(), AnswerKind, Connection (+18 more)

### Community 10 - "tracing.py"
Cohesion: 0.10
Nodes (25): concurrent_futures, contextvars, copy, functools, inspect, Single-worker local request queue with progress and cooperative cancellation., connection(), db_path() (+17 more)

### Community 11 - "mcp_server.py"
Cohesion: 0.06
Nodes (34): importlib_metadata, load_document_pdf(), doctor(), main(), Local service diagnostics and a terminal client for Jenna., add_arguments(), build_server(), ask_jenna() (+26 more)

### Community 12 - "test_pdf_visual.py"
Cohesion: 0.12
Nodes (11): font(), main(), make_document(), raster(), Actual local-model PDF image/handwriting development checks in an isolated…, hashlib, io, PDF visual extraction and original-pixel verification contracts. (+3 more)

### Community 13 - "sample_test.py"
Cohesion: 0.09
Nodes (15): bm25_search(), embed_batch(), safe_embed(), embed_chunks(), parallel_embed(), evaluate_retrieval(), filter_results(), get_embedding() (+7 more)

### Community 14 - "run"
Cohesion: 0.07
Nodes (36): asyncio, assess(), experiment(), load_dataset(), main(), Versioned, split-aware local-agent experiments over synthetic MCP fixtures., Scenario, benchmark() (+28 more)

### Community 15 - "web_tools.py"
Cohesion: 0.17
Nodes (18): main(), search_and_answer(), generate_document_answer(), plan_question_parts(), Preserve explicit question clauses without asking a model to omit any., RuntimeError, run_online_search(), fetch_web() (+10 more)

### Community 16 - "json"
Cohesion: 0.14
Nodes (12): argparse, csv, Export human review forms and compare human labels to automatic grades., main(), Development regression: local numerical planning and inline-code assistance. No…, Real-model web-evidence regression; Tavily transport alone is mocked., json, main() (+4 more)

### Community 17 - "JobManager"
Cohesion: 0.07
Nodes (12): JobManager, DeadlineExceeded, RuntimeError, RequestCancelled, ConversationTests, handler(), Model, APITests (+4 more)

### Community 18 - "app.py"
Cohesion: 0.42
Nodes (9): list_chats(), clear_active_chat(), delete_saved_chat(), display_passages(), display_retrieval_failure(), play_spoken_reply(), select_chat(), start_new_chat() (+1 more)

### Community 19 - "run_calculation"
Cohesion: 0.15
Nodes (7): calculate(), checked(), evaluate(), Plan unit-aware word problems; execute only validated bounded arithmetic., Evaluate bounded arithmetic without eval() or arbitrary execution., run_calculation(), CalculationCodeTests

### Community 21 - "prepare_data.py"
Cohesion: 0.20
Nodes (16): collections, gc, random, sqlite3, statistics, main(), Compare the same MLX base weights with and without local adapters., score() (+8 more)

### Community 22 - "api.py"
Cohesion: 0.17
Nodes (14): fastapi, fastapi_responses, list_traces(), cancel(), health(), job(), job_events(), Loopback REST API for Jenna jobs, traces, and readiness. (+6 more)

### Community 25 - "run_auto_documents.py"
Cohesion: 0.27
Nodes (6): flow_checks(), main(), pdf_bytes(), Auto source-boundary and full-flow development benchmarks using isolated PDFs.…, AutoBenchmarkScoringTests, The benchmark must not reward crashes, refusals, or another person's resume.

### Community 26 - "integrations/mcp_client.py"
Cohesion: 0.22
Nodes (20): oauth_provider(), answer_evidence(), ask(), ask_legacy(), execute_jira(), generate(), call_read_tool(), catalog() (+12 more)

### Community 27 - "document_store.py"
Cohesion: 0.26
Nodes (15): Time library calls, which cannot be decorated at their definition., timed_call(), add_document(), delete_document(), index_and_store_document(), _index_snapshot(), list_documents(), Remove the saved PDF and index; restore index if SQLite deletion fails. (+7 more)

### Community 28 - "chat_memory.py"
Cohesion: 0.22
Nodes (17): clear_chat_history(), delete_chat(), load_document_records(), save_document(), database(), delete(), fetch_record(), fetch_records() (+9 more)

### Community 29 - "search_utils.py"
Cohesion: 0.19
Nodes (12): main(), Evaluate the application's actual Chroma retrieval and reranker separately., search_documents(), create_embedding(), get_reranker(), lexical_search(), Combine multiple ranked retrieval lists using Reciprocal Rank Fusion (RRF).…, reciprocal_rank_fusion() (+4 more)

### Community 30 - "agent_service.py"
Cohesion: 0.28
Nodes (12): clarification_selection(), decide_action(), Resolve an exact selection from 'Do you mean X or Y?'., resolve_followup(), run_agent(), is_direct_conversation(), is_document_inventory_request(), is_local_code_request() (+4 more)

### Community 33 - "test_conversation.py"
Cohesion: 0.24
Nodes (11): assess(), main(), percentile(), Exercise the real app pipeline against an isolated, labeled synthetic corpus., main(), turn(), Sequential actual-model dialogue development evaluation, isolated from personal…, Control (+3 more)

### Community 34 - "Jenna AI"
Cohesion: 0.14
Nodes (13): Automatic intent and sources, Conversation and follow-ups, Direct MCP integrations, Engineering tools, Evaluate the current application, Jenna AI, Local fine-tuning, Numerical word problems and supplied code (+5 more)

### Community 35 - "calculator.py"
Cohesion: 0.35
Nodes (11): parse_vector(), memory_request(), handle_memory_command(), list_notes(), cosine_similarity(), run_cosine_search_and_calculate(), run_search_and_calculate(), make_result() (+3 more)

### Community 39 - "test_core.py"
Cohesion: 0.12
Nodes (9): forget_note(), recall_note(), remember_note(), normalize_key(), AppSmokeTests, CoreTests, f(), IngestionTests (+1 more)

### Community 40 - "jenna_personality.md"
Cohesion: 0.40
Nodes (4): Behavior, Document Handling & Constraints, Personality, Role & Identity

### Community 42 - "VisualExtractionTests"
Cohesion: 0.09
Nodes (4): image_pdf(), VisualExtractionTests, VisualIndexTests, VisualVerificationTests

### Community 46 - "llm.py"
Cohesion: 0.18
Nodes (10): atexit, dataclasses, httpx2, Cooperative cancellation, deadlines, and read-only retry controls., event(), reject(), close_clients(), Close pooled transports at process shutdown or explicit service teardown. (+2 more)

### Community 67 - "add_source_details"
Cohesion: 0.32
Nodes (3): add_source_details(), requests_source_details(), SourceCitationTests

### Community 68 - "timed_step"
Cohesion: 0.16
Nodes (11): checkpoint(), Named method timing for synchronous and asynchronous operations., timed_step(), page_image(), Keep page context and zoom substantial images obscured by native headings.…, read_visual_page(), verify_visual_sources(), visual_page_images() (+3 more)

### Community 69 - "EngineeringTests"
Cohesion: 0.21
Nodes (3): layout_pages(), EngineeringTests, handler()

### Community 70 - "os"
Cohesion: 0.11
Nodes (15): contextlib, Direct connections to external MCP servers., Literal local web credential lookup without executing shell configuration., Source-boundary regressions with intentionally incorrect model routing., ClientArchitectureTests, Shared provider lifecycle and request isolation; no inference or network calls., ConfigTests, Outbound MCP contracts, bounded planning, and credential storage. (+7 more)

### Community 71 - "timings.py"
Cohesion: 0.31
Nodes (7): display_timings(), Shared request and upload timing presentation., Presentation-ready timing rows; all durations are measured wall seconds., slowest_steps(), timing_rows(), request(), select()

### Community 72 - "visual_content_passage"
Cohesion: 0.40
Nodes (3): For a uniquely named short image, read its transcription, not its label., visual_content_passage(), VisualContentTests

### Community 73 - "assistant_service.py"
Cohesion: 0.23
Nodes (21): jsonschema, context_messages(), general_reply(), load_state(), natural_summary(), Synthesize a cited answer only after extractive evidence validation succeeds., Keep recent turns plus relevant older turns; state carries goals/constraints., rewrite_reply() (+13 more)

### Community 76 - "mcp_auth.py"
Cohesion: 0.18
Nodes (9): http_server, PersistentOAuthProvider, SDK OAuth storage and an interactive loopback login callback., Restore SDK refresh prerequisites that are otherwise process-local., mcp_client_auth, mcp_client_auth_oauth2, OAuthClientProvider, urllib_parse (+1 more)

### Community 78 - "cache.py"
Cohesion: 0.28
Nodes (4): credential_key(), Small TTL cache for stable read metadata, scoped to connection credentials., TTLCache, token_storage()

### Community 79 - "table_relation_error"
Cohesion: 0.33
Nodes (5): normalize(), Check short table values against their labels without model knowledge., table_relation_error(), table_field_pattern(), TableRelationTests

### Community 80 - "retry_read"
Cohesion: 0.32
Nodes (5): Retry transient transport failures only; caller must enforce read-only policy., retry_read(), execute(), RetryTests, read()

### Community 81 - "record_call"
Cohesion: 0.43
Nodes (5): record_call(), chat(), request(), inner(), outer()

### Community 82 - "rag_experiments.py"
Cohesion: 0.60
Nodes (4): main(), pdf(), Isolated RAG ablations: chunking, dense/hybrid retrieval, and reranking., worker()

## Knowledge Gaps
- **17 isolated node(s):** `graphify`, `Run`, `Use`, `Evaluate the current application`, `Local fine-tuning` (+12 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 330 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **37 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `build_server()` connect `mcp_server.py` to `assistant_service.py`, `calculator.py`, `enums.py`, `pathlib`?**
  _High betweenness centrality (0.057) - this node is a cross-community bridge._
- **Why does `load_prompt()` connect `assistant_service.py` to `plan_request`, `rag_service.py`, `run_assistant`, `timed_step`, `calculator.py`, `Jenna AI`, `jira_workflow.py`, `enums.py`, `mcp_server.py`, `run`, `web_tools.py`, `run_calculation`, `integrations/mcp_client.py`, `agent_service.py`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **Why does `run()` connect `run` to `rag_service.py`, `calculator.py`, `timed_step`, `os`, `jira_workflow.py`, `enums.py`, `assistant_service.py`, `tracing.py`, `llm.py`, `integrations/mcp_client.py`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `run_assistant()` (e.g. with `AnswerKind` and `Connection`) actually correct?**
  _`run_assistant()` has 6 INFERRED edges - model-reasoned connections that need verification._
- **What connects `graphify`, `Run`, `Use` to the rest of the system?**
  _17 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `plan_request` be split into smaller, more focused modules?**
  _Cohesion score 0.09361393323657474 - nodes in this community are weakly interconnected._
- **Should `rag_service.py` be split into smaller, more focused modules?**
  _Cohesion score 0.14666666666666667 - nodes in this community are weakly interconnected._