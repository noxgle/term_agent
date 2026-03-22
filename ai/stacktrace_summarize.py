import re

def summarize_stacktrace(
    text: str,
    max_chars: int = 1000,
    tail_bias: bool = True,
    tail_ratio: float = 0.7
) -> str:
    """
    Summarize a stacktrace, keeping error lines and highlighting the likely error location.

    Args:
        text: Raw stacktrace
        max_chars: Maximum characters for the preview
        tail_bias: Whether to prioritize the bottom of the trace
        tail_ratio: Ratio of max_chars allocated to the bottom

    Returns:
        Formatted summary string
    """

    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    if not lines:
        return "STACKTRACE:\n- empty"

    # --- helper: build char-limited preview ---
    def build_preview(lines, max_chars, tail_bias, tail_ratio):
        if sum(len(l)+1 for l in lines) <= max_chars:
            return "\n".join(lines)

        if tail_bias:
            bottom_budget = int(max_chars * tail_ratio)
            top_budget = max_chars - bottom_budget
        else:
            top_budget = bottom_budget = max_chars // 2

        top_part, bottom_part = [], []
        used = 0
        for l in lines:
            if used + len(l) + 1 > top_budget:
                break
            top_part.append(l)
            used += len(l) + 1

        used = 0
        for l in reversed(lines):
            if used + len(l) + 1 > bottom_budget:
                break
            bottom_part.append(l)
            used += len(l) + 1
        bottom_part.reverse()

        if top_part and bottom_part:
            return "\n".join(top_part) + "\n...\n" + "\n".join(bottom_part)
        elif top_part:
            return "\n".join(top_part)
        else:
            return "\n".join(bottom_part)

    # --- znajdź linie z error ---
    error_lines = [l for l in lines if re.search(r'error|exception|traceback', l, re.I)]
    # linie wskazujące miejsce błędu
    file_lines = [l for l in lines if re.search(r'\.py|\.java|\.js|\.cpp|\.ts', l)]

    # scal wszystkie ważne linie
    important_lines = list(dict.fromkeys(error_lines + file_lines))  # unikalne

    # jeśli mamy mniej ważnych linii niż max_chars → dodaj trochę kontekstu
    preview = build_preview(lines, max_chars, tail_bias, tail_ratio)

    summary = "STACKTRACE SUMMARY:\n"
    if important_lines:
        summary += "- highlighted error/location lines:\n"
        for l in important_lines[:10]:
            summary += f"  {l}\n"
    summary += "- preview (char-limited):\n"
    summary += preview

    return summary