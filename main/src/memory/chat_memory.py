from main.src.utils.enums import Role
import uuid
import json

from main.src.memory.memory_service import database, insert, fetch_records, fetch_record, update, delete, upsert


def create_chat():
    chat_id = uuid.uuid4().hex

    insert("chats", {"id": chat_id, "title": "New chat"})
    return chat_id


def list_chats():
    rows = fetch_records(
        "chats",
        ["id", "title"],
        order_by="updated_at DESC, rowid DESC"
    )

    return [
        {"id": chat_id, "title": title}
        for chat_id, title in rows
    ]

def clear_chat_history(chat_id):
    with database() as db: db.execute('DELETE FROM conversation_state WHERE session_id=?', (chat_id,))
    delete(
        "chat_messages",
        {"chat_id": chat_id},
    )

    update(
        "chats",
        {"title": 'New chat', "updated_at": "strftime('%Y-%m-%d %H:%M:%f', 'now')"},
        {"id": chat_id}
    )


def delete_chat(chat_id):
    with database() as db: db.execute('DELETE FROM conversation_state WHERE session_id=?', (chat_id,))
    delete(
        "chat_messages",
        {"chat_id": chat_id},
    )

    return delete(
        "chats",
        {"id": chat_id},
    )


def save_message(chat_id, message):
    if message.get("role") not in {Role.USER, Role.ASSISTANT}:
        raise ValueError("Invalid message role.")

    if not isinstance(message.get("content"), str):
        raise ValueError("Message content must be text.")

    payload = json.dumps(message, ensure_ascii=False)

    chat = fetch_record(
        "chats",
        ["id"],
        where={"id": chat_id},
    )

    if chat is None:
        raise ValueError("Chat does not exist.")

    previous_message = fetch_record(
        "chat_messages",
        ["id"],
        where={"chat_id": chat_id},
    )

    if previous_message is None and message["role"] == Role.USER:
        title = " ".join(message["content"].split())[:60]

        update(
            "chats",
            {"title": title or "New chat"},
            {"id": chat_id}
        )

    insert(
        "chat_messages",
        {"chat_id": chat_id, "payload": payload},
    )
    update(
        "chats",
        {"updated_at": "strftime('%Y-%m-%d %H:%M:%f', 'now')"},
        {"id": chat_id}
    )


def load_messages(chat_id, limit=100):
    if type(limit) is not int or limit < 1:
        raise ValueError("History limit must be a positive integer.")

    rows = fetch_records(
        "chat_messages",
        ["payload"],
        {"chat_id": chat_id},
        "id DESC",
        limit=limit,
    )

    return [
        json.loads(payload)
        for (payload,) in reversed(rows)
    ]
