import re
import json
from .table_summarizer import (
    summarize_ps, 
    summarize_df, 
    summarize_free, 
    summarize_netstat, 
    summarize_docker_ps, 
    summarize_top,
    summarize_generic_table
)


def detect_output_type(text: str, command: str = None) -> str:
    """
    Detects the type of output from a given text string.
    """

    # --- multi-command guard ---
    if command and "&&" in command:
        return "text"  # docelowo: "multi_text"

    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return "empty"

    sample = lines[:20]
    joined = "\n".join(sample)

    # --- 1. Stacktrace ---
    if any("Traceback (most recent call last)" in l for l in sample):
        return "stacktrace"

    if any(re.search(r'\bat\s+\S+\(.*\)', l) for l in sample):
        return "stacktrace"

    # --- 2. Logi (dmesg + timestampy) ---

    # 🔥 dmesg pattern: [ 123.456 ]
    if any(re.match(r'^\[\s*\d+\.\d+\]', l) for l in sample):
        return "log"

    timestamp_patterns = [
        r'\d{4}-\d{2}-\d{2}',
        r'\d{2}:\d{2}:\d{2}',
        r'\w{3}\s+\d+\s+\d{2}:\d{2}:\d{2}'
    ]

    timestamp_hits = sum(
        any(re.search(p, l) for p in timestamp_patterns)
        for l in sample
    )

    if timestamp_hits > len(sample) * 0.3:
        return "log"

    # --- 3. JSON (dopiero po logach!) ---
    try:
        parsed = json.loads(joined)
        if isinstance(parsed, (dict, list)):
            return "json"
    except Exception:
        pass

    # --- 4. Tabele ---
    header = lines[0]
    header_cols = header.split()

    if len(header_cols) >= 4:
        similar = 0
        for l in lines[1:10]:
            cols = l.split()
            if abs(len(cols) - len(header_cols)) <= 2:
                similar += 1

        if similar >= 3:
            return "table"

    # --- 5. Key-value ---
    kv_hits = sum(1 for l in sample if "=" in l and not l.startswith(" "))
    if kv_hits > len(sample) * 0.4:
        return "kv"

    # --- 6. Single line ---
    if len(lines) == 1:
        return "single_line"

    # --- 7. Default ---
    return "text"


def summarize_table(text: str) -> str:
    """
    Summarize table output based on detected table type.

    Args:
        text: Raw table output text

    Returns:
        Formatted summary string
    """
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return "TABLE:\n- empty output"

    header = lines[0].lower()

    # --- detekcja znanych narzędzi ---
    if "pid" in header and "cpu" in header:
        return summarize_ps(text)

    if "filesystem" in header and "use%" in header:
        return summarize_df(text)

    if "mem:" in text.lower():
        return summarize_free(text)

    if "proto" in header and "local address" in header:
        return summarize_netstat(text)

    if "container id" in header:
        return summarize_docker_ps(text)

    # --- heurystyka dla 'top' / 'htop' ---
    if any(k in text.lower() for k in ["load average", "zadania", "miB ram", "pid"]):
        return summarize_top(text)

    # --- fallback ---
    return summarize_generic_table(text)


def summarize_multi_command_preview(command: str, output: str, max_chars: int = 800, tail_bias: bool = True, tail_ratio: float = 0.7) -> str:
    """
    Summarize output for a command with && in a single string output.
    Splits output by heuristics (separators) and applies summarizers + top-bottom preview.

    Args:
        command: full shell command (may contain &&)
        output: single string with combined output of all sub-commands
        max_chars: max characters per preview
        tail_bias: whether to favor bottom
        tail_ratio: fraction of chars for bottom preview

    Returns:
        Combined summary string
    """
    # --- heurystyczny split po separatorach lub nagłówkach ---
    # próbujemy znaleźć linie typu ---SEKCJA--- lub nagłówki ps/df
    split_pattern = r'^(---.*---|USER\s+PID|Filesystem\s+|CONTAINER ID\s+|Proto\s+)'  # regex dla typowych header/echo separator
    lines = output.splitlines()
    sections = []
    current_section = []

    for l in lines:
        if re.match(split_pattern, l):
            if current_section:
                sections.append("\n".join(current_section))
                current_section = []
        current_section.append(l)
    if current_section:
        sections.append("\n".join(current_section))

    summaries = []

    for i, sec in enumerate(sections):
        sec = sec.strip()
        if not sec:
            continue
        header = f"SECTION {i+1}" if len(sections) > 1 else ""

        out_type = detect_output_type(sec, command=command)
        sec_lines = [l.rstrip() for l in sec.splitlines() if l.strip()]

        # --- helper: top+bottom preview ---
        def build_preview(lines, max_chars, tail_bias, tail_ratio):
            if not lines:
                return ""
            total_len = sum(len(l)+1 for l in lines)
            if total_len <= max_chars:
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

        # --- wybór summarizera ---
        if out_type == "table":
            summary = summarize_table(sec, max_chars=max_chars, tail_bias=tail_bias, tail_ratio=tail_ratio)
        elif out_type == "kv":
            summary = summarize_kv(sec, max_chars=max_chars, tail_bias=tail_bias, tail_ratio=tail_ratio)
        elif out_type == "stacktrace":
            summary = summarize_stacktrace(sec, max_chars=max_chars, tail_bias=tail_bias, tail_ratio=tail_ratio)
        elif out_type == "json":
            summary = summarize_json(sec, max_chars=max_chars)
        else:
            summary = build_preview(sec_lines, max_chars, tail_bias, tail_ratio)

        if header:
            summary = f"{header}:\n{summary}"
        summaries.append(summary)

    return "\n\n".join(summaries)