from main.src.utils.enums import Action, ResultStatus
import json

from main.src.utils.common_utils import make_result
from main.src.memory.memory_service import upsert, delete, fetch_records, fetch_record
from main.src.utils.common_utils import normalize_key
from main.src.utils.diagnostics import debug


def remember_note(key, value, provenance=None):
    key = normalize_key(key)

    if not isinstance(value, str):
        raise ValueError("Memory value must be text.")

    value = value.strip()

    if not value or len(value) > 1000:
        raise ValueError("Use a memory value of 1–1000 characters.")

    upsert(
        "personal_notes",
        {"key": key, "value": value, "provenance": json.dumps(provenance or {"source": "explicit_command"})},
        "key"
    )

    return key


def recall_note(key):
    key = normalize_key(key)
    row = fetch_record(
        "personal_notes",
        ["value"],
        where={"key": key},
    )

    return row[0] if row else None


def forget_note(key):
    key = normalize_key(key)

    return delete("personal_notes", {"key": key})


def list_notes():
    rows = fetch_records(
        "personal_notes",
        ["key", "value"],
        order_by="key"
    )

    return dict(rows)

def note_details(key):
    import json
    row = fetch_record('personal_notes', ['value', 'provenance', 'updated_at'], where={'key': normalize_key(key)})
    return {'value': row[0], 'provenance': json.loads(row[1]), 'updated_at': row[2]} if row else None


def handle_memory_command(question):
    text = question.strip()
    lowered = text.casefold()

    if lowered.startswith("remember:"):
        action = Action.REMEMBER_NOTE
    elif lowered.startswith("recall:"):
        action = Action.RECALL_NOTE
    elif lowered.startswith("forget:"):
        action = Action.FORGET_NOTE
    elif lowered == "memories":
        action = Action.LIST_NOTES
    else:
        return None

    try:
        if action == Action.REMEMBER_NOTE:
            body = text.split(":", 1)[1].strip()
            key, separator, value = body.partition("=")

            if not separator:
                raise ValueError(
                    "Use: remember: key = value"
                )

            key = remember_note(key, value)
            answer = f"Saved personal note: {key}."

        elif action == Action.RECALL_NOTE:
            key = text.split(":", 1)[1].strip()
            value = recall_note(key)

            answer = (
                f"Saved personal note — {key}: {value}"
                if value is not None
                else f"I don't have a saved note for '{key}'."
            )

        elif action == Action.FORGET_NOTE:
            key = text.split(":", 1)[1].strip()
            deleted = forget_note(key)

            answer = (
                f"Deleted personal note: {key}."
                if deleted
                else f"I don't have a saved note for '{key}'."
            )

        else:
            notes = list_notes()

            answer = (
                "Your saved personal notes:\n\n"
                + "\n".join(
                    f"- {key}: {value}"
                    for key, value in notes.items()
                )
                if notes
                else "You have no saved personal notes."
            )

        return make_result(
            answer,
            ResultStatus.MEMORY_COMPLETED,
            action,
            tools_used=[action],
        )

    except ValueError as error:
        return make_result(
            str(error),
            ResultStatus.INVALID_MEMORY_REQUEST,
            action,
        )

    except Exception as error:
        debug("MEMORY ERROR:", type(error).__name__, str(error))

        return make_result(
            "I couldn't complete the memory operation. Please try again.",
            ResultStatus.MEMORY_ERROR,
            action,
            tools_used=[action],
        )
