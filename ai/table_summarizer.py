"""
Table summarization functions for different types of system command outputs.
"""

import re
from typing import List, Tuple, Optional

def summarize_top(text: str, max_chars: int = 800, tail_bias: bool = True, tail_ratio: float = 0.7) -> str:
    """
    Summarize 'top' command output:
    - separates key-value metrics from process table
    - applies char-limited preview with tail bias
    """

    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    if not lines:
        return "TABLE:\n- empty output"

    # --- znajdź linię nagłówka procesów ---
    split_index = None
    for i, l in enumerate(lines):
        if "pid" in l.lower() and "cpu" in l.lower():
            split_index = i
            break

    if split_index is None:
        # fallback: traktuj całość jako key-value
        return summarize_generic_table(text)

    kv_lines = lines[:split_index]
    proc_lines = lines[split_index:]

    # --- helper: build char-limited preview ---
    def build_preview(lines, max_chars, tail_bias, tail_ratio):
        if not lines:
            return ""
        total_len = sum(len(l) + 1 for l in lines)
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

    # --- generowanie podsumowania ---
    result = ""
    if kv_lines:
        result += "TABLE (key-value metrics):\n"
        result += f"- rows: {len(kv_lines)}\n"
        result += f"- preview (char-limited):\n{build_preview(kv_lines, max_chars, tail_bias, tail_ratio)}\n"

    if proc_lines:
        # header table
        proc_header = proc_lines[0].split()
        result += "\nTABLE (processes):\n"
        result += f"- rows: {len(proc_lines) - 1}\n"
        result += f"- columns: {len(proc_header)}\n"
        result += f"- header: {proc_header}\n"
        result += f"- preview (char-limited):\n{build_preview(proc_lines, max_chars, tail_bias, tail_ratio)}\n"

    return result


def summarize_ps(text: str) -> str:
    """
    Summarize process table output (ps aux format).

    Args:
        text: Raw ps aux output

    Returns:
        Formatted summary string
    """
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        return "PROCESS SNAPSHOT:\n- total processes: 0\n- root processes: 0\n- max CPU usage: 0.00%\n"

    header = lines[0].split()
    procs = lines[1:]

    total = len(procs)

    # kolumna USER - szukamy jej indeksu w nagłówku
    try:
        user_idx = header.index("USER")
    except ValueError:
        user_idx = 0  # fallback: pierwsza kolumna

    # kolumna %CPU
    try:
        cpu_idx = header.index("%CPU")
    except ValueError:
        cpu_idx = 2  # fallback: trzecia kolumna

    root_count = 0
    cpu_values = []

    for l in procs:
        parts = l.split(None, len(header)-1)  # split na max kolumn
        if len(parts) <= max(user_idx, cpu_idx):
            continue

        if parts[user_idx] == "root":
            root_count += 1

        try:
            cpu_values.append(float(parts[cpu_idx]))
        except ValueError:
            continue

    top_cpu = max(cpu_values) if cpu_values else 0

    # Pobierz pierwsze 10 linii wyniku
    first_10_lines = lines[:10]
    
    result = f"""PROCESS SNAPSHOT:
- total processes: {total}
- root processes: {root_count}
- max CPU usage: {top_cpu:.2f}%

FIRST 10 LINES:
{chr(10).join(first_10_lines)}
"""
    
    return result


def summarize_df(text: str) -> str:
    """
    Summarize disk usage table output (df -h format).
    
    Args:
        text: Raw df -h output
        
    Returns:
        Formatted summary string
    """
    lines = text.splitlines()[1:]
    if not lines:
        return "DISK USAGE:\n- disks: 0\n"

    disks = []
    critical = []

    for l in lines:
        parts = l.split()
        if len(parts) < 6:
            continue

        fs, size, used, avail, use_pct, mount = parts[:6]

        try:
            usage = int(use_pct.replace("%", ""))
        except (ValueError, IndexError):
            continue

        disks.append((mount, usage))

        if usage > 80:
            critical.append((mount, usage))

    summary = [f"- disks: {len(disks)}"]

    if critical:
        summary.append("- high usage:")
        for m, u in critical:
            summary.append(f"  - {m}: {u}%")

    return "DISK USAGE:\n" + "\n".join(summary)


def summarize_free(text: str) -> str:
    """
    Summarize memory usage table output (free -h format).
    
    Args:
        text: Raw free -h output
        
    Returns:
        Formatted summary string
    """
    lines = text.splitlines()

    mem_line = next((l for l in lines if l.lower().startswith("mem:")), None)
    swap_line = next((l for l in lines if l.lower().startswith("swap:")), None)

    def parse(line: Optional[str]) -> Optional[Tuple[str, str, str]]:
        if not line:
            return None
        parts = line.split()
        if len(parts) < 4:
            return None
        return parts[1], parts[2], parts[3]

    mem = parse(mem_line) if mem_line else None
    swap = parse(swap_line) if swap_line else None

    result = ["MEMORY:"]

    if mem:
        total, used, free = mem
        result.append(f"- RAM total: {total}")
        result.append(f"- RAM used: {used}")
        result.append(f"- RAM free: {free}")

    if swap:
        total, used, free = swap
        result.append(f"- SWAP used: {used}")

    return "\n".join(result)


def summarize_netstat(text: str) -> str:
    """
    Summarize network connection table output (netstat/ss format).

    Args:
        text: Raw netstat or ss output

    Returns:
        Formatted summary string
    """
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return "NETWORK:\n- total connections: 0\n- listening: 0\n- established: 0"

    # Spróbuj wykryć nagłówek (linia z "Proto" lub "State")
    header_idx = 0
    for i, l in enumerate(lines):
        if "proto" in l.lower() or "state" in l.lower():
            header_idx = i
            break

    conn_lines = lines[header_idx + 1:] if header_idx + 1 < len(lines) else []

    total = len(conn_lines)
    listening = 0
    established = 0

    for l in conn_lines:
        state = l.strip().split()[0] if l.strip() else ""
        # bezpieczne wykrywanie LISTEN/ESTABLISHED niezależnie od wielkości liter
        if "listen" in l.lower():
            listening += 1
        if "established" in l.lower():
            established += 1

    return f"""NETWORK:
- total connections: {total}
- listening: {listening}
- established: {established}
"""

def summarize_docker_ps(text: str) -> str:
    """
    Summarize Docker container table output (docker ps format).
    
    Args:
        text: Raw docker ps output
        
    Returns:
        Formatted summary string
    """
    lines = text.splitlines()[1:]
    if not lines:
        return "DOCKER CONTAINERS:\n- total: 0\n"

    total = len(lines)

    images = {}
    for l in lines:
        parts = l.split()
        if len(parts) < 2:
            continue

        image = parts[1]
        images[image] = images.get(image, 0) + 1

    result = [f"DOCKER CONTAINERS:"]
    result.append(f"- total: {total}")

    if images:
        result.append("- by image:")
        for img, count in list(images.items())[:5]:
            result.append(f"  - {img}: {count}")

    return "\n".join(result)


def summarize_generic_table(
    text: str,
    max_chars: int = 2000,
    tail_bias: bool = True,
    tail_ratio: float = 0.7
) -> str:
    MAX_LINE_LEN = 400

    # --- normalize lines ---
    def normalize_line(l: str, max_len: int) -> str:
        clean = l.rstrip()
        return clean[:max_len] + "..." if len(clean) > max_len else clean

    lines = [
        normalize_line(l, MAX_LINE_LEN)
        for l in text.splitlines()
        if l.strip()
    ]
    
    if not lines:
        return "TABLE:\n- empty output"

    total_lines = len(lines)

    # --- helper: build preview under char budget ---
    def build_preview(lines, max_chars, tail_bias, tail_ratio):
        if not lines:
            return ""

        total_len = sum(len(l) + 1 for l in lines)
        if total_len <= max_chars:
            return "\n".join(lines)

        if tail_bias:
            bottom_budget = int(max_chars * tail_ratio)
            top_budget = max_chars - bottom_budget
        else:
            top_budget = bottom_budget = max_chars // 2

        # --- take from top ---
        top_part = []
        used = 0
        for l in lines:
            if used + len(l) + 1 > top_budget:
                break
            top_part.append(l)
            used += len(l) + 1

        # --- take from bottom ---
        bottom_part = []
        used = 0
        for l in reversed(lines):
            if used + len(l) + 1 > bottom_budget:
                break
            bottom_part.append(l)
            used += len(l) + 1
        bottom_part.reverse()

        # --- merge ---
        if top_part and bottom_part:
            return "\n".join(top_part) + "\n...\n" + "\n".join(bottom_part)
        elif top_part:
            return "\n".join(top_part)
        else:
            return "\n".join(bottom_part)

    preview = build_preview(lines, max_chars, tail_bias, tail_ratio)

    # --- detect key-value format ---
    kv_pattern = re.compile(r"^\s*\d+[\d\s]*\s+\w+")
    kv_matches = sum(1 for l in lines if kv_pattern.match(l))

    if kv_matches / total_lines > 0.6:
        return f"""TABLE (key-value):
- rows: {total_lines}
- detected: numeric metrics
- preview (char-limited):
{preview}
"""

    # --- detect column table ---
    split_lines = [re.split(r"\s{2,}|\t", l.strip()) for l in lines]
    col_counts = [len(cols) for cols in split_lines]

    avg_cols = sum(col_counts) / total_lines
    max_cols = max(col_counts)

    is_table = avg_cols >= 2

    if is_table:
        header = split_lines[0]
        return f"""TABLE:
- rows: {total_lines - 1}
- columns: {max_cols}
- header: {header}
- preview (char-limited):
{preview}
"""
    else:
        return f"""TEXT:
- lines: {total_lines}
- preview (char-limited):
{preview}
"""
