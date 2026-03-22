import re

def summarize_kv(
    text: str,
    max_chars: int = 800,
    tail_bias: bool = True,
    tail_ratio: float = 0.7
) -> str:
    """
    Summarize key-value output:
    - deduplicates keys (last value wins)
    - optionally applies char-limited preview

    Args:
        text: raw key-value output
        max_chars: max characters in preview
        tail_bias: whether to favor bottom of output
        tail_ratio: fraction of chars for bottom

    Returns:
        Formatted summary string
    """
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    if not lines:
        return "KEY-VALUE OUTPUT:\n- empty"

    # --- parse key-value ---
    kv_dict = {}
    pattern = re.compile(r'^\s*([\w\-\./]+)\s*[:=]\s*(.+)$')  # key: value lub key = value
    for l in lines:
        m = pattern.match(l)
        if m:
            key, value = m.groups()
            kv_dict[key] = value.strip()

    # --- rebuild lines, deduplicated ---
    dedup_lines = [f"{k}: {v}" for k, v in kv_dict.items()]

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

    preview = build_preview(dedup_lines, max_chars, tail_bias, tail_ratio)

    return f"KEY-VALUE OUTPUT:\n- total keys: {len(kv_dict)}\n- preview (char-limited):\n{preview}"