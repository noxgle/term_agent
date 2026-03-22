import json

def summarize_json(data, max_chars: int = 1000) -> str:
    """
    Pretty-print and truncate JSON output for feedback.

    Args:
        data: JSON string or Python dict/list
        max_chars: maximum number of characters in output

    Returns:
        Pretty-printed JSON string (truncated if needed)
    """
    # --- jeśli wejście jest string, spróbuj parsować ---
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return f"Invalid JSON:\n{data[:max_chars]}{'...' if len(data) > max_chars else ''}"

    # --- funkcja do rekursywnego truncate ---
    def truncate(obj, max_len):
        """
        Recursively truncate strings in JSON to max_len
        """
        if isinstance(obj, dict):
            return {k: truncate(v, max_len) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [truncate(v, max_len) for v in obj]
        elif isinstance(obj, str):
            return obj[:max_len] + ("..." if len(obj) > max_len else "")
        else:
            return obj

    truncated_data = truncate(data, 200)  # truncate każdą wartość string do 200 znaków

    pretty = json.dumps(truncated_data, indent=2, ensure_ascii=False)

    # --- skróć całość do max_chars ---
    if len(pretty) > max_chars:
        preview = pretty[:max_chars] + "\n..."
    else:
        preview = pretty

    return preview