# Graph Report - jenna-ai  (2026-10-23)

## Corpus Check
- 128 files · ~114,274 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 2, .example 1, .jsonl 1)

## Summary
- 1032 nodes · 3131 edges · 69 communities (32 shown, 37 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 221 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `3123f536`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- run_assistant
- tempfile
- test_mcp_client.py
- document_store.py
- os
- test_engineering.py
- FileTokenStorage
- jira_workflow.py
- OutboundTests
- assistant_service.py
- runtime.py
- build_server
- asyncio
- sample_test.py
- EngineeringTests
- app.py
- run_agent.py
- run_intent.py
- run_visual_documents.py
- checkpoint
- MCP Protocol Tests
- prepare_data.py
- run
- EvidenceTests
- Shared Client Tests
- cache.py
- rag_experiments.py
- LoginCallback
- enums.py
- CoreTests
- Client
- Jenna AI
- json
- AutoSearchTests
- Offline Evaluation Module
- Engineering Runtime Controls
- unittest
- jenna_personality.md
- test_pdf_visual.py
- AGENTS.md
- datasets/README.md
- integrations/mcp_client.py
- WebTests
- mcp_auth.py
- VoiceTests
- test_core.py

## God Nodes (most connected - your core abstractions)
1. `run_assistant()` - 55 edges
2. `get_client()` - 48 edges
3. `Role` - 43 edges
4. `run()` - 40 edges
5. `ResultStatus` - 38 edges
6. `plan_request()` - 37 edges
7. `load_prompt()` - 37 edges
8. `PromptName` - 37 edges
9. `Model` - 32 edges
10. `run_agent()` - 31 edges

## Surprising Connections (you probably didn't know these)
- `Shared constants and patterns` --references--> `load_prompt()`  [INFERRED]
  README.md → main/src/utils/common_utils.py
- `experiment()` --indirect_call--> `manifest()`  [INFERRED]
  evaluation/generalization.py → main/src/engineering/release.py
- `remote()` --indirect_call--> `jira_identifiers_supported()`  [INFERRED]
  evaluation/run_intent.py → main/src/integrations/mcp_client.py
- `main()` --calls--> `generate_document_answer()`  [EXTRACTED]
  evaluation/run_web_evidence.py → main/src/rag/rag_service.py
- `plan_request()` --calls--> `validate()`  [INFERRED]
  main/src/agent/assistant_service.py → training/validate_data.py

## Import Cycles
- None detected.

## Communities (69 total, 37 thin omitted)

### Community 0 - "run_assistant"
Cohesion: 0.07
Nodes (12): matches_uploaded_document(), plan_request(), run_assistant(), verify(), exact_anchor_pattern(), ArithmeticFollowupTests, AssistantTests, Model (+4 more)

### Community 1 - "tempfile"
Cohesion: 0.18
Nodes (10): ast, concurrent_futures, main(), Development regression: local numerical planning and inline-code assistance. No…, main(), Real-model web-evidence regression; Tavily transport alone is mocked., ClientArchitectureTests, Shared provider lifecycle and request isolation; no inference or network calls. (+2 more)

### Community 2 - "test_mcp_client.py"
Cohesion: 0.22
Nodes (6): contextlib, Direct connections to external MCP servers., ConfigTests, Outbound MCP contracts, bounded planning, and credential storage., mcp_types, stat

### Community 3 - "document_store.py"
Cohesion: 0.27
Nodes (11): add_document(), index_and_store_document(), _index_snapshot(), Remove partial replacement writes and restore even overlapping chunk IDs., _restore_index(), lexical_search(), Combine multiple ranked retrieval lists using Reciprocal Rank Fusion (RRF).…, reciprocal_rank_fusion() (+3 more)

### Community 4 - "os"
Cohesion: 0.20
Nodes (11): atexit, main(), get_reranker(), rerank_retrieved(), close_clients(), Measured Ollama client shared by routing and evidence selection., Close pooled transports at process shutdown or explicit service teardown., ModelOperation (+3 more)

### Community 5 - "test_engineering.py"
Cohesion: 0.26
Nodes (12): main(), make_pdf(), Actual PDF ingestion and local-app evaluation on new documents, tables, and OCR., behavior_fingerprint_matches(), gate(), manifest(), Content-addressed manifests and measurable release gates., sha() (+4 more)

### Community 7 - "jira_workflow.py"
Cohesion: 0.10
Nodes (23): has_jira_intent(), A person's name alone does not establish a Jira lookup., active_sprint_request(), active_sprints(), read(), assigned_work(), read(), cell() (+15 more)

### Community 8 - "OutboundTests"
Cohesion: 0.12
Nodes (9): Model, OutboundTests, connection(), connection(), plan(), Session, HTTPIntegrationTests, client() (+1 more)

### Community 9 - "assistant_service.py"
Cohesion: 0.07
Nodes (95): chromadb, jsonschema, logging, clarification_selection(), decide_action(), Resolve an exact selection from 'Do you mean X or Y?'., resolve_followup(), run_agent() (+87 more)

### Community 10 - "runtime.py"
Cohesion: 0.07
Nodes (18): contextvars, dataclasses, natural_summary(), Synthesize a cited answer only after extractive evidence validation succeeds., JobManager, DeadlineExceeded, RuntimeError, Cooperative cancellation, deadlines, and read-only retry controls. (+10 more)

### Community 11 - "build_server"
Cohesion: 0.12
Nodes (19): build_server(), ask_jenna(), backend(), calculate(), documents_data(), documents_resource(), forget_note(), list_chats() (+11 more)

### Community 12 - "asyncio"
Cohesion: 0.21
Nodes (9): asyncio, main(), A minimal MCP client that connects to Jenna via stdio or local HTTP., use_session(), MCPBackendTests, mcp, mcp_client_stdio, mcp_client_streamable_http (+1 more)

### Community 13 - "sample_test.py"
Cohesion: 0.09
Nodes (15): bm25_search(), embed_batch(), safe_embed(), embed_chunks(), parallel_embed(), evaluate_retrieval(), filter_results(), get_embedding() (+7 more)

### Community 15 - "app.py"
Cohesion: 0.07
Nodes (52): datetime, faster_whisper, fragment, functools, hashlib, kokoro, load_state(), save_state() (+44 more)

### Community 16 - "run_agent.py"
Cohesion: 0.24
Nodes (9): assess(), main(), percentile(), Exercise the real app pipeline against an isolated, labeled synthetic corpus., main(), turn(), Sequential actual-model dialogue development evaluation, isolated from personal…, Control (+1 more)

### Community 17 - "run_intent.py"
Cohesion: 0.38
Nodes (4): Scenario, main(), remote(), Actual local-model intent/typo checks, with isolated document and MCP fixtures.

### Community 18 - "run_visual_documents.py"
Cohesion: 0.48
Nodes (5): font(), main(), make_document(), raster(), Actual local-model PDF image/handwriting development checks in an isolated…

### Community 19 - "checkpoint"
Cohesion: 0.20
Nodes (12): checkpoint(), Retry transient transport failures only; caller must enforce read-only policy., retry_read(), event(), ask(), execute(), Use one general local tool-calling agent for every MCP server/question., run_mcp_question() (+4 more)

### Community 21 - "prepare_data.py"
Cohesion: 0.21
Nodes (15): collections, gc, random, statistics, main(), Compare the same MLX base weights with and without local adapters., score(), encode() (+7 more)

### Community 22 - "run"
Cohesion: 0.06
Nodes (43): assess(), experiment(), load_dataset(), main(), Versioned, split-aware local-agent experiments over synthetic MCP fixtures., benchmark(), request(), main() (+35 more)

### Community 25 - "cache.py"
Cohesion: 0.22
Nodes (5): copy, credential_key(), Small TTL cache for stable read metadata, scoped to connection credentials., TTLCache, threading

### Community 26 - "rag_experiments.py"
Cohesion: 0.31
Nodes (8): main(), pdf(), Isolated RAG ablations: chunking, dense/hybrid retrieval, and reranking., worker(), request_trace(), instrument_request(), execute(), measured()

### Community 29 - "enums.py"
Cohesion: 0.06
Nodes (50): BaseModel, enum, fastapi, fastapi_responses, importlib_metadata, Single-worker local request queue with progress and cooperative cancellation., connection(), db_path() (+42 more)

### Community 33 - "Client"
Cohesion: 0.13
Nodes (6): Client, Administrative generation, used to unload models in benchmarks., Collect token deltas while publishing bounded local job/UI progress., record_call(), inner(), outer()

### Community 34 - "Jenna AI"
Cohesion: 0.14
Nodes (13): Automatic intent and sources, Conversation and follow-ups, Direct MCP integrations, Engineering tools, Evaluate the current application, Jenna AI, Local fine-tuning, Numerical word problems and supplied code (+5 more)

### Community 35 - "json"
Cohesion: 0.13
Nodes (15): argparse, csv, Export human review forms and compare human labels to automatic grades., Evaluate the application's actual Chroma retrieval and reranker separately., huggingface_hub, json, pathlib, sys (+7 more)

### Community 39 - "unittest"
Cohesion: 0.18
Nodes (9): flow_checks(), main(), pdf_bytes(), Auto source-boundary and full-flow development benchmarks using isolated PDFs.…, io, AutoBenchmarkScoringTests, The benchmark must not reward crashes, refusals, or another person's resume., unittest (+1 more)

### Community 40 - "jenna_personality.md"
Cohesion: 0.40
Nodes (4): Behavior, Document Handling & Constraints, Personality, Role & Identity

### Community 42 - "test_pdf_visual.py"
Cohesion: 0.09
Nodes (7): image_pdf(), PDF visual extraction and original-pixel verification contracts., VisualExtractionTests, VisualIndexTests, VisualVerificationTests, pil, pymupdf

### Community 46 - "integrations/mcp_client.py"
Cohesion: 0.23
Nodes (19): oauth_provider(), token_storage(), answer_evidence(), ask_legacy(), execute_jira(), call_read_tool(), catalog(), compact_evidence() (+11 more)

### Community 67 - "mcp_auth.py"
Cohesion: 0.16
Nodes (11): http_server, httpx2, PersistentOAuthProvider, SDK OAuth storage and an interactive loopback login callback., Restore SDK refresh prerequisites that are otherwise process-local., mcp_client_auth, mcp_client_auth_oauth2, mcp_shared_auth (+3 more)

### Community 72 - "test_core.py"
Cohesion: 0.12
Nodes (8): normalize(), Check short table values against their labels without model knowledge., table_relation_error(), table_field_pattern(), IngestionTests, RoutingTests, TableRelationTests, WebEvidenceRecoveryTests

## Knowledge Gaps
- **17 isolated node(s):** `graphify`, `Run`, `Use`, `Evaluate the current application`, `Local fine-tuning` (+12 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 313 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **37 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `run_assistant()` connect `run_assistant` to `tempfile`, `unittest`, `assistant_service.py`, `runtime.py`, `integrations/mcp_client.py`, `app.py`, `run_agent.py`, `run_intent.py`, `run_visual_documents.py`, `checkpoint`, `rag_experiments.py`, `enums.py`?**
  _High betweenness centrality (0.037) - this node is a cross-community bridge._
- **Why does `load_prompt()` connect `assistant_service.py` to `run_assistant`, `Jenna AI`, `runtime.py`, `build_server`, `integrations/mcp_client.py`, `run`, `enums.py`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._
- **Why does `EvidenceTests` connect `EvidenceTests` to `test_core.py`?**
  _High betweenness centrality (0.032) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `run_assistant()` (e.g. with `AnswerKind` and `Connection`) actually correct?**
  _`run_assistant()` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 27 inferred relationships involving `Role` (e.g. with `clarification_selection()` and `decide_action()`) actually correct?**
  _`Role` has 27 INFERRED edges - model-reasoned connections that need verification._
- **What connects `graphify`, `Run`, `Use` to the rest of the system?**
  _17 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `run_assistant` be split into smaller, more focused modules?**
  _Cohesion score 0.06862745098039216 - nodes in this community are weakly interconnected._