from typing import Any


def normalize_message_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for item in content:
            text = _extract_text(item)
            if text:
                text_parts.append(text)
        if text_parts:
            return "\n".join(text_parts)
        return str(content)
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text
        if text is not None:
            return normalize_message_text(text)
        nested_content = content.get("content")
        if nested_content is not None:
            return normalize_message_text(nested_content)
    return str(content)


def normalize_message_role(message_type: Any) -> str:
    normalized_type = str(message_type or "").lower()
    if normalized_type == "ai":
        return "ai"
    return "user"


def _extract_text(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        text = item.get("text")
        if isinstance(text, str):
            return text
        if text is not None:
            return normalize_message_text(text)
        nested_content = item.get("content")
        if nested_content is not None:
            return normalize_message_text(nested_content)
    return ""
