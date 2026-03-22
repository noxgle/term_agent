import re
from .table_summarizer import (
    summarize_ps, 
    summarize_df, 
    summarize_free, 
    summarize_netstat, 
    summarize_docker_ps, 
    summarize_top,
    summarize_generic_table
)

def detect_output_type(text: str) -> str:
    """
    Detects the type of output from a given text string.
    
    Analyzes the text content and categorizes it into one of several output types:
    - json: Text starting with { or [
    - stacktrace: Python or Java stack traces
    - log: Log entries with timestamps
    - table: Structured data with headers and similar rows
    - kv: Key-value pairs (e.g., environment variables)
    - single_line: Single line output
    - text: Default fallback for regular text
    - empty: Empty or whitespace-only text
    
    Args:
        text: The text to analyze
        
    Returns:
        A string indicating the detected output type
    """
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return "empty"

    sample = lines[:20]
    joined = "\n".join(sample)

    # --- 1. JSON ---
    if joined.strip().startswith("{") or joined.strip().startswith("["):
        return "json"

    # --- 2. Stacktrace (Python, Java, etc.)
    if any("Traceback (most recent call last)" in l for l in sample):
        return "stacktrace"

    if any(re.search(r'\bat\s+\S+\(.*\)', l) for l in sample):  # Java
        return "stacktrace"

    # --- 3. Logi (timestamp + powtarzalność struktury)
    timestamp_patterns = [
        r'\d{4}-\d{2}-\d{2}',                # 2026-03-20
        r'\d{2}:\d{2}:\d{2}',                # 14:55:01
        r'\w{3}\s+\d+\s+\d{2}:\d{2}:\d{2}'   # Mar 20 14:55:01
    ]

    timestamp_hits = sum(
        any(re.search(p, l) for p in timestamp_patterns)
        for l in sample
    )

    if timestamp_hits > len(sample) * 0.3:
        return "log"

    # --- 4. Tabele (np. ps aux, df -h)
    # Heurystyka: pierwsza linia = nagłówki, dużo kolumn
    header = lines[0]
    header_cols = header.split()

    if len(header_cols) >= 4:
        # sprawdzamy czy kolejne linie mają podobną strukturę
        similar = 0
        for l in lines[1:10]:
            cols = l.split()
            if abs(len(cols) - len(header_cols)) <= 2:
                similar += 1

        if similar >= 3:
            return "table"

    # --- 5. Key-value (np. env, config)
    kv_hits = sum(1 for l in sample if "=" in l and not l.startswith(" "))
    if kv_hits > len(sample) * 0.4:
        return "kv"

    # --- 6. Jednolinijkowy output (np. echo, error)
    if len(lines) == 1:
        return "single_line"

    # --- 7. Domyślnie: zwykły tekst
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
