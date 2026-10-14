# Jenna AI

A local personal assistant with general conversation, streamed replies, shared session
state, PDF evidence search, bounded tool routing, arithmetic, editable personal
preferences, persistent chats, optional web search, and local speech.
The application uses pretrained models; uploading PDFs indexes evidence rather than
training the model. A separate local QLoRA workflow trains task behavior.

## Run

Python 3.12 is the verified runtime. From the project root:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
ollama pull qwen3.5:9b
ollama pull nomic-embed-text
.venv/bin/python -m main.src.tools.cli doctor
.venv/bin/streamlit run main/src/app.py
```

Keep Ollama running. The reranker downloads on the first document question; voice models
load only when used. The existing environment already has the runtime dependencies.
`requirements.lock.txt` records direct dependency versions verified on this Mac, rather
than claiming to be a complete transitive dependency lock.

Configuration is described in `.env.example`. Export variables before launching the app;
the application does not automatically source `.env`. For example:

```sh
export JENNA_CONTEXT_K=8
export JENNA_CANDIDATE_K=40
```

Web mode needs `TAVILY_API_KEY` in the environment. The resolved question is sent to
Tavily; document context and saved notes are not sent to the web-search service.
A question can itself contain personal information. Without a key, web mode reports
its configuration error. Document mode remains local.

## Use

Ask naturally in Automatic mode. General knowledge, learning, writing and coding
answer directly; private or current factual requests select the relevant source.
Upload PDFs in the sidebar for document questions. Source overrides are optional.
For local factual retrieval, Auto tries documents, then web when no verified answer
is available. Explicit questions about your own documents stay local. Documents
mode searches only PDFs; Web searches online; Documents + Web combines both.
If basic web excerpts cannot support an answer, Jenna makes at most one advanced
Tavily retry, requesting more relevant passages. This adds search latency and Tavily
credits only on the recovery path. Failed answers show retrieved excerpts and the
evidence-check reason in an expander. Saved PDFs
can be downloaded or deleted. Scanned PDFs require OCR before upload; OCR is not
implemented. Search results include supporting quotations and page references.
Document answers can become readable cited summaries after quotation checks and semantic
verification; unsuccessful synthesis retains the original extractive answer.

Examples:

- `Calculate sqrt(81) + 15 / 100 * 200`
- `List my uploaded documents.`
- `remember: preferred_language = Python`
- `recall: preferred_language`
- `memories`
- `forget: preferred_language`

Microphone input lets you review the transcript before sending. Spoken responses use
Kokoro Alice, British English. Chat clearing/deletion and note deletion affect local storage.
PDF deletion removes the saved PDF and its search index, but does not erase quotations
already saved in chat history or data/model artifacts previously exported for training.

## Evaluate the current application

```sh
.venv/bin/python -m unittest discover -s main/tests -v
.venv/bin/python -m evaluation.run_agent --output reports/agent-baseline.json
.venv/bin/python -m evaluation.run_retrieval --limit 20
```

The agent suite creates an isolated synthetic corpus and temporary memory database.
It tests answers, routing, arithmetic, follow-ups, multipart completeness, missing
information, source instructions, notes, and tool composition. It preserves your saved
PDFs, chats, and notes. Nonzero exit means at least one case failed.

Retrieval evaluation searches your current corpus using the actual Chroma pipeline.
It reports candidate and final-context hit rates, MRR, labeled precision/recall, and timing.
Missing legacy label locations are explicitly excluded. It does not certify answer quality.
Use `--dense-only`, `--candidate-k`, and `--context-k` for controlled comparisons.

See [engineering guide](docs/ENGINEERING.md) for design choices and evaluation limits,
and [completion report](docs/COMPLETION.md) for the measured local results.

## Local fine-tuning

Apple Silicon training is isolated from the application environment:

```sh
python3.12 -m venv .venv-training
.venv-training/bin/python -m pip install -r requirements-training.txt
.venv-training/bin/python training/download_model.py
.venv-training/bin/python training/run.py --include-project-data
.venv-training/bin/python training/evaluate.py
```

Omit `--include-project-data` to train on synthetic examples only. With it, the dataset
uses saved document passages, supported chat pairs, and existing notes. Generated data,
checkpoints, and reports stay local. Review the dataset before subsequent training runs.
The current saved adapter was trained using the project data authorized in this chat.

The runner validates schemas, duplicate inputs, split separation, and token lengths before
training. Training uses 4-bit Llama 3.2 3B, LoRA rank 8 on four layers, 100 steps,
batch size 1, learning rate 0.0001, prompt masking, and a fixed seed.
Data partitions group document pages and synthetic template families. The small test
partition is a development holdout, not an independent production benchmark.

Export to an Ollama-compatible GGUF and register locally:

```sh
.venv/bin/python -m pip install -r requirements-export.txt
.venv/bin/python training/export.py --register
.venv/bin/python -m evaluation.run_agent --model jenna-finetuned:latest --output reports/agent-finetuned.json
```

The export runner fuses the adapter, uses a pinned official llama.cpp converter,
and writes a Q8_0 GGUF. It downloads converter source when absent. The verified deployment uses GGUF and the standard latest tag. Earlier native-format
and custom-tag imports were listed but unavailable to this installation's chat API.
Registration remains local.
The trained Llama adapter remains an optional candidate; Qwen 3.5 9B is now the default local model.
You may still evaluate the adapter as a router with an explicitly selected chat model:

```sh
.venv/bin/python -m evaluation.run_agent --router-model jenna-finetuned:latest --output reports/agent-finetuned-router.json
JENNA_ROUTER_MODEL=jenna-finetuned:latest .venv/bin/streamlit run main/src/app.py
```

Global promotion requires non-regression on routing, evidence, and conversation, followed
by the real-app suite. Low validation loss alone does not justify replacing the model.

## Storage and scope

Local storage is `main/jenna_memory/`; use an absolute `JENNA_MEMORY_PATH` to isolate another
instance. Preserve this directory to preserve chats, notes, PDFs, and the vector index.
Changing embedding models requires rebuilding a separate index; existing embeddings are
not interchangeable. Set `JENNA_MEMORY_PATH` to a new directory and upload the PDFs again.

This is a single-user local application. It is not a deployed multi-tenant service and does
not implement authentication, tenant isolation, distributed workers, or production monitoring.
`backup/` contains historical implementations and benchmarks; `main/` is the maintained app.

## Direct MCP integrations

Choose **OpenAI MCP** or **Jira · Swirepay SPD** in the sidebar's **Connection** selector. OpenAI connects directly to its official documentation MCP server; Jira uses Atlassian MCP with browser OAuth. Jenna also serves its own tools over stdio or local Streamable HTTP for other MCP clients. Setup, client configurations, authentication, and testing are in [docs/MCP.md](docs/MCP.md).

## Stronger local reasoning

Jenna's MCP agent uses **Qwen 3.5 9B** with native tool calling and discovered MCP schemas. It handles new questions through a general reasoning loop rather than phrase-specific Jira routes. Install it with `ollama pull qwen3.5:9b`; configuration, limits, and model evaluations are in [docs/LOCAL_MODEL.md](docs/LOCAL_MODEL.md). No cloud inference or per-question fine-tuning is required.

## Engineering tools

The project now includes 80 split-aware evaluation cases, human-review exports, persisted local traces, bounded tool/schema context, PDF tables/OCR, metadata filters, controlled RAG ablations, cold/warm performance checks, queued requests with progress/cancellation, a loopback REST API, Postman contracts, and release/CI gates. Commands, limitations, and privacy behavior are in [docs/ENGINEERING_UPGRADE.md](docs/ENGINEERING_UPGRADE.md).

## Automatic intent and sources

Jenna now defaults to automatic source selection: ask naturally about a Jira ticket,
a PDF, or an online fact without switching connection/mode first. A local intent
interpreter handles ordinary typos and clear follow-ups; source controls remain optional
overrides. See [natural requests and automatic sources](docs/DYNAMIC_ROUTING.md) for
behavior, privacy, verification and evaluation limitations.

## Conversation and follow-ups

Jenna can explain concepts, brainstorm, write and revise answers without another search.
Session goals, corrections and constraints persist. Natural saved-preference requests
work across chats; the sidebar lets you inspect, edit and forget them. General replies
stream in the UI and through `/jobs/{id}/events`; source-backed replies wait for verification.
See [conversation workflow and evaluations](docs/CONVERSATION.md) for implementation,
API usage, privacy and limits. Run `python -m evaluation.run_conversation` for the new
actual-model multi-turn development suite.

## Shared constants and patterns

`main/src/utils/enums.py` defines the shared modes, intents, actions, roles, result/job
statuses, source kinds, transports, authentication types and prompt names. These use
Python `StrEnum` to retain the existing JSON and SQLite string values. Model defaults,
numeric limits and environment settings remain in `utils/constants.py`.

Runtime regex definitions, pattern groups and escaped identifier builders live in
`main/src/utils/regex_constants.py`; matching flags remain explicit at their call sites.
Add new patterns there. The contract tests check centralization, identifier boundaries,
prompt inputs and wire compatibility. All owned JSON schemas, REST models, MCP parameter
types and dynamic schema builders live in `utils/schemas.py`. Static client instructions
of up to three authored lines live in `utils/instructions.py`; longer prompts live as
Markdown under `main/instructions`. `load_prompt` handles both locations, including the
short-prompt registry. Some newly extracted Markdown files use soft line wrapping;
their loader folds those wraps to preserve the exact original model input.
User text, chat history and retrieved evidence are assembled dynamically rather than
saved as instruction files. The measured model client remains under `tools/llm.py`.

## Numerical word problems and supplied code

In automatic mode, numerical word problems use a local calculation planner before
the restricted AST calculator. The planner explains the formula and unit conversions,
or asks for missing inputs; the calculator computes the result. For example,
`calculate BMI - age 24 - height 174 cm and weight 80kg` uses
`80 / (174 / 100) ** 2`, giving approximately `26.4236`. Age is not a term in this
formula. Explicit arithmetic continues to bypass planning. Powers are bounded to
exponents from -12 to 12, and arbitrary Python execution remains prohibited.
The model's formula interpretation can still be wrong; a valid schema or arithmetic
expression does not prove the semantic correctness of a new formula.

Requests to debug, fix or explain supplied code use conversational reasoning in
automatic mode, with no document/web evidence requirement. Jenna explains syntax
and runtime problems and proposes corrected code; it does not execute that code.
Explicit document, web or connection overrides retain their source behavior.
Run `.venv/bin/python -m evaluation.run_calculation_code` for the small actual-model
development regression and `.venv/bin/python -m unittest discover -s main/tests` for
software regression checks. Generated-code checks parse Python without executing it.
