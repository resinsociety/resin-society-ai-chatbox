from collections import defaultdict, deque

# Simple in-memory conversation memory.
# Works immediately on Railway, but resets when the app restarts.
# Later we can upgrade this to Redis/Postgres if needed.
CONVERSATION_MEMORY = defaultdict(lambda: deque(maxlen=10))


def add_message(conversation_id, role, content):
    if not conversation_id or not content:
        return

    CONVERSATION_MEMORY[str(conversation_id)].append({
        "role": role,
        "content": content
    })


def get_memory(conversation_id):
    return list(CONVERSATION_MEMORY.get(str(conversation_id), []))


def build_memory_text(conversation_id):
    messages = get_memory(conversation_id)

    if not messages:
        return ""

    lines = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        lines.append(f"{role}: {content}")

    return "\n".join(lines)


def get_last_user_messages(conversation_id, limit=5):
    messages = get_memory(conversation_id)
    user_messages = [m["content"] for m in messages if m.get("role") == "user"]
    return user_messages[-limit:]


def build_contextual_user_message(conversation_id, current_message):
    previous = get_last_user_messages(conversation_id, limit=5)

    if not previous:
        return current_message

    return "\n".join(previous + [current_message])