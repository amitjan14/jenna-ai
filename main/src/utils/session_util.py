from main.src.utils.enums import SourceKind
import streamlit as st

from main.src.memory.chat_memory import load_messages, create_chat, delete_chat, list_chats, clear_chat_history
from main.src.tools.voice import synthesize_speech


def select_chat(chat_id):
    st.session_state.active_chat_id = chat_id
    st.session_state.messages = load_messages(chat_id, limit=100)
    st.query_params['chat'] = chat_id

def start_new_chat():
    select_chat(create_chat())

def delete_saved_chat(chat_id):
    was_active = (
        chat_id == st.session_state.get("active_chat_id")
    )

    deleted = delete_chat(chat_id)

    if not deleted or not was_active:
        return

    remaining_chats = list_chats()

    if remaining_chats:
        select_chat(remaining_chats[0]["id"])
    else:
        start_new_chat()

def clear_active_chat():
    chat_id = st.session_state.active_chat_id
    clear_chat_history(chat_id)
    st.session_state.messages = []

def play_spoken_reply(text, autoplay=False):
    try:
        with st.spinner("Preparing spoken reply..."):
            audio_bytes = synthesize_speech(text)

        st.audio(
            audio_bytes,
            format="audio/wav",
            autoplay=autoplay,
        )

    except Exception as error:
        st.warning(f"Couldn't generate speech: {error}")

def display_passages(passages):
    if not passages:
        return

    with st.expander("📚 Supporting passages"):
        for source in passages:
            if source.get("kind") == SourceKind.WEB:
                st.write(f"Web: {source['filename']}")

                st.markdown(
                    f"[Open web source](<{source['url']}>)"
                )

                st.caption(
                    f"Retrieved: {source.get('retrieved_at', 'unknown')}"
                )
            else:
                st.write(
                    f"{source['filename']} — "
                    f"Page {source['page']} — "
                    f"Chunk {source['chunk_index']}"
                )

            st.write(source["quote"])

def display_retrieval_failure(message):
    sources = message.get("retrieved_sources", [])
    if not sources:
        return
    with st.expander("Retrieved sources — why no answer?"):
        if message.get("rejection_reason"):
            st.caption(message["rejection_reason"])
        for source in sources:
            st.write(source.get("filename", "Source"))
            if source.get("url"):
                st.markdown(f"[Open source](<{source['url']}>)")
            st.text(source.get("text", ""))
