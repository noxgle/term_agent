"""
Log Compressor - kompresja logów poprzez maskowanie zmiennych i grupowanie powtórzeń.
"""

import re
import logging
from collections import defaultdict
from sentence_transformers import SentenceTransformer
from sklearn.cluster import DBSCAN
import numpy as np
import os

#os.environ["CUDA_VISIBLE_DEVICES"] = ""

def should_compress(log_text: str) -> bool:
    lines = [l for l in log_text.splitlines() if l.strip()]
    
    if len(lines) < 20:
        return False

    unique_ratio = len(set(lines)) / len(lines)

    if unique_ratio < 0.7:
        return True

    if len(log_text) > 5000:
        return True

    return False

def should_compress_adaptive(log_text: str) -> bool:
    lines = [l for l in log_text.splitlines() if l.strip()]
    n = len(lines)
    unique_ratio = len(set(lines)) / max(n, 1)

    if n < 20 and unique_ratio > 0.7:
        return False  # mało, unikalne → nie kompresuj

    if n >= 20 or unique_ratio < 0.7 or len(log_text) > 5000:
        return True

    return False

class LogCompressor:
    """
    Kompresuje logi poprzez:
    1. Maskowanie zmiennych wartości (czas, liczby, PID-y, itp.)
    2. Grupowanie identycznych template'ów
    3. Sortowanie wg częstości występowania
    """

    def __init__(self):
        # regexy do "maskowania" zmiennych
        self.patterns = [
            (re.compile(r'\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'), '<TIME>'),
            (re.compile(r'\b\d+\b'), '<NUM>'),
            (re.compile(r'\b[0-9a-f]{6,}\b', re.IGNORECASE), '<HEX>'),
            (re.compile(r'\b(pid|uid)=\d+\b'), r'\1=<NUM>'),
        ]

    def normalize(self, line: str) -> str:
        """
        Usuwa zmienne i tworzy template z linii logu.

        Args:
            line: Pojedyncza linia logu.

        Returns:
            Znormalizowany template linii.
        """
        line = line.strip()

        for pattern, repl in self.patterns:
            line = pattern.sub(repl, line)

        return line

    def compress(self, log_text: str) -> str:
        """
        Kompresuje tekst logów poprzez grupowanie identycznych linii.

        Args:
            log_text: Pełny tekst logów do skompresowania.

        Returns:
            Skompresowany tekst logów z template'ami i licznikiem powtórzeń.
        """
        groups = defaultdict(int)

        for line in log_text.splitlines():
            if not line.strip():
                continue

            template = self.normalize(line)
            groups[template] += 1

        # sortowanie: najczęstsze na górze
        sorted_groups = sorted(groups.items(), key=lambda x: -x[1])

        output = []
        for template, count in sorted_groups:
            if count == 1:
                output.append(template)
            else:
                output.append(f"{template} x{count}")

        return "\n".join(output)

class DynamicLogCompressor:
    def __init__(self, model_name="sentence-transformers/all-MiniLM-L6-v2", dir_app=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        
        os.environ["CUDA_VISIBLE_DEVICES"] = ""      # wymuszenie CPU
        os.environ["TRANSFORMERS_CACHE"] = f"{dir_app}/hf_cache" if dir_app else "/app/hf_cache"
        self.logger.debug(f"HF cache directory: {dir_app}/hf_cache")

        # --- Ładowanie modelu lokalnie ---
        try:
            self.logger.info(f"Loading model from local cache: {model_name}")
            self.model = SentenceTransformer(model_name, device="cpu", local_files_only=True)
        except Exception as e:
            self.logger.error(f"Failed to load model from local cache: {e}")
            raise RuntimeError(f"Could not load local model {model_name}") from e

        self.patterns = [
            (re.compile(r'\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'), '<TIME>'),
            (re.compile(r'\b\d+\b'), '<NUM>'),
            (re.compile(r'\b[0-9a-f]{6,}\b', re.IGNORECASE), '<HEX>'),
        ]

    # --- NORMALIZACJA ---
    def normalize(self, line: str) -> str:
        for pattern, repl in self.patterns:
            line = pattern.sub(repl, line)
        return line.strip()

    # --- EMBEDDING ---
    def embed(self, lines):
        return self.model.encode(lines, show_progress_bar=False)

    # --- CLUSTERING ---
    def cluster(self, embeddings):
        clustering = DBSCAN(
            eps=0.2,         # czułość (ważne!)
            min_samples=2,
            metric="cosine"
        ).fit(embeddings)

        return clustering.labels_

    # --- GŁÓWNA FUNKCJA ---
    def compress(self, log_text: str):
        raw_lines = [l for l in log_text.splitlines() if l.strip()]
        normalized = [self.normalize(l) for l in raw_lines]

        if len(normalized) < 5:
            return "\n".join(normalized)

        embeddings = self.embed(normalized)
        labels = self.cluster(embeddings)

        clusters = defaultdict(list)

        for line, label in zip(normalized, labels):
            clusters[label].append(line)

        output = []

        for label, lines in clusters.items():
            if label == -1:
                # outliery (unikalne)
                output.extend(lines)
                continue

            # wybierz reprezentanta (najkrótszy / najczęstszy)
            rep = min(lines, key=len)

            output.append(f"{rep} x{len(lines)}")

        return "\n".join(output)