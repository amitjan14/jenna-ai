import hashlib
import os
import sys
from pathlib import Path
import streamlit as st

# Streamlit adds the script directory to sys.path, but imports need the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from main.src.utils.enums import Connection, ExecutionStatus, Role, SearchMode, SourceKind
from main.src.utils.constants import DEFAULT_CHAT_MODEL

from main.src.engineering.jobs import manager
from main.src.engineering.tracing import list_traces, read_trace
from main.src.integrations.mcp_client import load_servers, discover, run_mcp_question
import asyncio
from main.src.memory.chat_memory import list_chats, create_chat, save_message
from main.src.memory.document_memory import load_document_records, load_document_pdf
from main.src.rag.document_store import index_and_store_document, delete_document
from main.src.utils.constants import CHAT_MODEL, ROUTER_MODEL
from main.src.utils.session_util import play_spoken_reply, display_passages, delete_saved_chat, select_chat, \
    clear_active_chat, start_new_chat, display_retrieval_failure
from main.src.tools.voice import transcribe_audio

st.set_page_config(
    page_title="Jenna AI",
    page_icon=str(PROJECT_ROOT / "main/assets/favicon.png"),
    layout="wide",
)

st.title("Jenna AI")
st.subheader("Personal AI Assistant")
st.logo(
    image=str(PROJECT_ROOT / "main/assets/logo.png"),
    icon_image=str(PROJECT_ROOT / "main/assets/favicon.png"),
    link="http://localhost:8501"
)

chats = list_chats()
known_chat_ids = {chat["id"] for chat in chats}

requested_chat = st.query_params.get('chat')
active_chat = st.session_state.get("active_chat_id")

if requested_chat in known_chat_ids:
    selected_chat = requested_chat
elif active_chat in known_chat_ids:
    selected_chat = active_chat
elif chats:
    selected_chat = chats[0]["id"]
else:
    selected_chat = create_chat()

if (
        st.session_state.get("active_chat_id") != selected_chat
        or "messages" not in st.session_state
):
    select_chat(selected_chat)
else:
    st.query_params['chat'] = selected_chat

# Migrate existing sessions once to the new automatic default.
if not st.session_state.get('automatic_routing_enabled'):
    st.session_state.mcp_connection = Connection.AUTO
    st.session_state.source_mode = SearchMode.AUTO
    st.session_state.document_scope = 'All documents'
    st.session_state.automatic_routing_enabled = True

with st.sidebar:
    with st.expander("Request traces"):
        trace_rows = list_traces(20)
        if trace_rows:
            selected_trace = st.selectbox("Trace", [row["id"] for row in trace_rows], key="trace_selection")
            st.json(read_trace(selected_trace))
        else:
            st.caption("Traces will appear after a request.")
    st.caption("Ask naturally. Jenna chooses the source from your request and conversation.")
    with st.expander("Advanced source overrides"):
        mcp_servers = load_servers()
        integration = st.selectbox("Routing", [Connection.AUTO, Connection.LOCAL, *mcp_servers], key="mcp_connection",
            format_func=lambda name: "Automatic · understand my request" if name == Connection.AUTO else "Jenna local tools" if name == Connection.LOCAL else mcp_servers[name].get("label", name))
        if integration not in {Connection.AUTO, Connection.LOCAL}:
            st.caption(f"Local MCP model: {os.getenv('JENNA_MCP_MODEL', DEFAULT_CHAT_MODEL)}")
            st.caption("Tool arguments, which may include your question and follow-up context, are sent to this MCP server.")
            if integration == "jira":
                st.caption("Site: swirepay.atlassian.net · Project: SPD")
                st.code(".venv/bin/python -m main.src.integrations.mcp_client login jira", language="bash")
            if st.button("Test MCP connection"):
                try:
                    with st.spinner("Discovering MCP tools..."):
                        remote_tools = asyncio.run(discover(integration))
                    st.success(f"Connected · {len(remote_tools)} read tools")
                    st.write([tool["name"] for tool in remote_tools])
                except Exception:
                    st.error("MCP connection failed. Check the endpoint and authentication. For Jira, run the sign-in command above.")
            st.divider()
        st.caption("Automatic routing chooses Jira, documents or web from your request. Controls below are optional overrides.")
        st.subheader("Source overrides")
        st.caption(f"Chat: {CHAT_MODEL} · Router: {ROUTER_MODEL}")

        search_mode = st.selectbox(
            "Sources for factual questions",
            [SearchMode.AUTO, SearchMode.DOCUMENTS, SearchMode.WEB, SearchMode.DOCUMENTS_AND_WEB],
            key="source_mode",
            disabled=integration not in {Connection.AUTO, Connection.LOCAL},
        )
        document_scope=st.selectbox('PDF scope',['All documents',*sorted(load_document_records())],key='document_scope',disabled=integration not in {Connection.AUTO,Connection.LOCAL})

        if search_mode == SearchMode.AUTO:
            st.caption("Try documents first, then the web if evidence is missing. Questions about your own documents stay local.")

        if search_mode != SearchMode.DOCUMENTS:
            st.caption(
                "The resolved search question is sent to Tavily. "
                "PDF contents and saved notes stay local."
            )

        st.divider()
    with st.expander('Saved preferences'):
        from main.src.memory.note_memory import list_notes, note_details, remember_note, forget_note
        preferences=list_notes()
        if preferences:
            selected_preference=st.selectbox('Preference',list(preferences),key='preference_edit_key')
            details=note_details(selected_preference)
            import hashlib
            version=hashlib.sha256(details['value'].encode()).hexdigest()[:12]
            edited_value=st.text_area('Saved value',value=details['value'],key='pref_value_'+selected_preference+'_'+version)
            st.json({'provenance':details['provenance'],'updated_at':details['updated_at']})
            if st.button('Save preference edit'):
                remember_note(selected_preference,edited_value,provenance={'source':'ui_edit'})
                st.rerun()
            if st.button('Forget preference'):
                forget_note(selected_preference);st.rerun()
        else:
            st.caption('Ask Jenna to remember a preference for future chats. You can edit or forget it here.')
    st.subheader("Voice")

    voice_input_enabled = st.checkbox(
        "Enable microphone input",
        value=False,
        key="voice_input_enabled",
    )

    voice_output_enabled = st.checkbox(
        "Enable spoken replies",
        value=False,
        key="voice_output_enabled",
    )

    st.caption("English transcription · Kokoro Alice · British English")
    st.divider()

    st.button(
        "➕ New Chat",
        use_container_width=True,
        on_click=start_new_chat,
    )

    st.button(
        "🗑️ Clear Current Chat",
        use_container_width=True,
        on_click=clear_active_chat,
        disabled=bool(st.session_state.get('pending_job')) and st.session_state.get('pending_chat') == st.session_state.active_chat_id,
    )

    st.divider()
    st.subheader("Previous Chats")

    for chat in list_chats():
        active = (
                chat["id"] == st.session_state.active_chat_id
        )

        label = (
            f"● {chat['title']}"
            if active
            else chat["title"]
        )

        open_column, delete_column = st.columns([4, 1])

        with open_column:
            st.button(
                label,
                key=f"chat_{chat['id']}",
                use_container_width=True,
                on_click=select_chat,
                args=(chat["id"],),
            )

        with delete_column:
            st.button(
                "🗑️",
                key=f"delete_chat_{chat['id']}",
                help=f"Delete chat: {chat['title']}",
                on_click=delete_saved_chat,
                args=(chat["id"],),
                disabled=bool(st.session_state.get('pending_job')) and st.session_state.get('pending_chat') == chat['id'],
            )

    st.divider()
    st.subheader("Upload Documents")

    uploaded_files = st.file_uploader(
        "Choose PDF files",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdf_uploader",
    )

    if "processed_uploads" not in st.session_state:
        st.session_state.processed_uploads = set()

    if uploaded_files:
        for uploaded_file in uploaded_files:
            pdf_bytes = uploaded_file.getvalue()
            content_hash = hashlib.sha256(pdf_bytes).hexdigest()
            upload_key = (uploaded_file.name, content_hash)

            if upload_key in st.session_state.processed_uploads:
                continue

            try:
                result = index_and_store_document(
                    pdf_bytes,
                    uploaded_file.name,
                )

                st.session_state.processed_uploads.add(upload_key)

                if result["status"] == "already_indexed":
                    st.info(
                        f"{uploaded_file.name} is already indexed."
                    )
                else:
                    st.success(
                        f"Indexed {uploaded_file.name}: "
                        f"{result['chunk_count']} chunks"
                    )

            except Exception as error:
                st.error(
                    f"Could not save/index {uploaded_file.name}: {error}"
                )

    # Outside `if uploaded_files`: visible after reload.
    st.divider()
    st.subheader("Saved PDFs")

    saved_documents = load_document_records()

    if saved_documents:
        for filename, record in saved_documents.items():
            st.write(
                f"{filename} — {record['chunk_count']} chunks"
            )
            pdf_bytes = load_document_pdf(filename)
            if pdf_bytes:
                st.download_button("Download PDF", pdf_bytes, file_name=filename,
                                   mime="application/pdf", key=f"download_{filename}")
            if st.button("Delete PDF", key=f"remove_{filename}"):
                try:
                    delete_document(filename)
                    st.session_state.processed_uploads = {
                        key for key in st.session_state.processed_uploads if key[0] != filename
                    }
                    st.rerun()
                except Exception as error:
                    st.error(f"Could not delete {filename}: {error}")
    else:
        st.caption("No saved PDFs yet.")


for index, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        if message.get("tools_used"):
            st.caption(
                "Tools used: " + ", ".join(message["tools_used"])
            )

        for notice in message.get("notices", []):
            st.caption(notice)
        if message.get("interpreted_question"):
            with st.expander("How Jenna understood the request"):
                st.write(message["interpreted_question"])
                st.caption("Selected connection: " + str(message.get("connection", Connection.LOCAL)))

        if message.get("metrics"):
            metrics = message["metrics"]
            st.caption(f"{metrics.get('total_seconds', 0):.2f}s · "
                       f"{metrics.get('llm_calls', 0)} model calls")
        display_passages(message.get("passages", []))
        display_retrieval_failure(message)
        if message.get("trace_id"):
            with st.expander("Request trace"):
                st.json(read_trace(message["trace_id"]))
        if message.get("mcp_evidence"):
            with st.expander("MCP tool evidence"):
                st.json(message["mcp_evidence"])
        if (
                voice_output_enabled
                and message["role"] == Role.ASSISTANT
        ):
            if st.button(
                    "🔊 Read aloud",
                    key=(
                            f"speak_{st.session_state.active_chat_id}_{index}"
                    ),
            ):
                play_spoken_reply(message["content"])

voice_prompt = None

if voice_input_enabled:
    chat_id = st.session_state.active_chat_id
    draft_key = f"voice_draft_{chat_id}"

    st.subheader("🎙️ Voice message")

    recording = st.audio_input(
        "Record your question",
        sample_rate=16000,
        key=f"voice_recording_{chat_id}",
    )

    if st.button(
        "Transcribe recording",
        disabled=recording is None,
        key=f"transcribe_{chat_id}",
    ):
        try:
            with st.spinner("Transcribing locally..."):
                transcript = transcribe_audio(
                    recording.getvalue()
                )

            # Set before the text-area widget is created.
            st.session_state[draft_key] = transcript

        except Exception as error:
            st.error(f"Couldn't transcribe the recording: {error}")

    st.session_state.setdefault(draft_key, "")

    draft = st.text_area(
        "Review or edit the transcript",
        key=draft_key,
    )

    if st.button(
        "Send voice message",
        disabled=not draft.strip(),
        key=f"send_voice_{chat_id}",
    ):
        voice_prompt = draft.strip()

typed_prompt = st.chat_input("Ask Jenna anything...")
prompt = voice_prompt or typed_prompt

if prompt:
    if st.session_state.get("pending_job"):
        st.warning("Finish or cancel the active request before sending another.")
    else:
        user_message = {"role": Role.USER, "content": prompt}
        save_message(st.session_state.active_chat_id, user_message)
        st.session_state.messages.append(user_message)
        job = manager.submit({"question": prompt, "connection": integration,
            "session_id": st.session_state.active_chat_id, "mode": search_mode, "history": st.session_state.messages[:-1], "timeout": 180,
            "filters": None if document_scope=='All documents' else {'filename':document_scope}})
        st.session_state.pending_job = job["id"]
        st.session_state.pending_chat = st.session_state.active_chat_id
        st.rerun()


@st.fragment(run_every=1)
def render_pending_request():
    job_id = st.session_state.get("pending_job")
    if not job_id:
        return
    job = manager.get(job_id)
    if not job:
        st.session_state.pop("pending_job", None)
        st.error("The request is no longer available. Please retry.")
        return
    if job["status"] in {ExecutionStatus.QUEUED, ExecutionStatus.RUNNING}:
        stage = job.get("progress", {}).get("stage", job["status"])
        st.status("Jenna: " + stage.replace("_", " "), state=ExecutionStatus.RUNNING)
        if job.get('partial_text'):
            with st.chat_message(Role.ASSISTANT):
                st.markdown(job['partial_text'] + ' ▌')
        st.caption("Cancellation takes effect between operations; an active model call may need to finish.")
        if st.button("Cancel request", key="cancel_pending"):
            manager.cancel(job_id)
        return
    chat_id = st.session_state.pending_chat
    if job["status"] == ExecutionStatus.COMPLETED:
        result = job["result"]
        passages = []
        for item in result.get("support", []):
            source = result["results"][item["source_id"]]
            passages.append({"kind": source.get("kind", SourceKind.DOCUMENT), "filename": source["filename"],
                "page": source.get("page"), "chunk_index": source.get("chunk_index"),
                "url": source.get("url"), "retrieved_at": source.get("retrieved_at"), "quote": item["quote"]})
        message = {"role": Role.ASSISTANT, "content": result["answer"], "support": result.get("support", []),
            "tools_used": result.get("tools_used", []), "status": result["status"], "passages": passages,
            "notices": result.get("notices", []), "metrics": result.get("metrics", {}),
            "rejection_reason": result.get("rejection_reason", ""), "retrieved_sources": result.get("retrieved_sources", []),
            "mcp_evidence": result.get("mcp_evidence", []), "trace_id": result.get("trace_id"),
            "connection": result.get("connection"), "interpreted_question": result.get("interpreted_question"),
            "conversation_state": result.get("conversation_state"), "answer_kind": result.get("answer_kind"),
            "results": result.get("results", []), "extractive_answer": result.get("extractive_answer")}
    else:
        message = {"role": Role.ASSISTANT, "content": "Request " + job["status"].replace("_", " ") + ". You can retry.",
                   "status": job["status"], "trace_id": job_id}
    save_message(chat_id, message)
    if chat_id == st.session_state.active_chat_id:
        st.session_state.messages.append(message)
    st.session_state.pop("pending_job", None)
    st.session_state.pop("pending_chat", None)
    st.rerun()


render_pending_request()
