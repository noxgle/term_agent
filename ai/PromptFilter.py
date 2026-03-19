"""
Prompt Filter Module for Vault 3000 AI Agent

Provides functions to clean and compress prompts before sending to AI models.
Reduces token usage by removing Markdown formatting, code blocks, and applying
heuristic abbreviations for common terms.

Usage:
    from ai.PromptFilter import compress_prompt, clean_url
    
    filtered_prompt = compress_prompt(raw_prompt)
"""

import re
import html
import json
from urllib.parse import urlparse, urlunparse


def clean_url(url: str) -> str:
    """
    Remove query and fragment from URL, keeping domain and path.
    
    Args:
        url: Full URL string
        
    Returns:
        Simplified URL without query parameters or fragments
    """
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))

def compress_prompt(text: str) -> str:
    """
    Lekki compressor promptu + próba naprawy JSON.
    Jeśli naprawa JSON się nie uda, zwraca dokładnie oryginalny tekst.
    
    UŻYCIE: Wyłącznie dla danych wejściowych od użytkownika lub API.
    NIE używać dla: wewnętrznych promptów systemowych, odpowiedzi AI,
    danych generowanych przez agenta.
    """
    original_text = text  # zachowaj oryginał

    if not text:
        return text

    # 1. Dekodowanie Unicode
    text = html.unescape(text)

    # 2. Markdown linki [text](url) → text (url)
    def replace_link(match):
        label = match.group(1)
        url = clean_url(match.group(2))
        return f"{label} ({url})"
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', replace_link, text)

    # 3. Usuwanie code block i inline code
    text = re.sub(r'```.*?```', '', text, flags=re.S)
    text = re.sub(r'`([^`]*)`', r'\1', text)

    # 4. Usuń markdown bold/italic/strike
    text = re.sub(r'(\*\*|__)(.*?)\1', r'\2', text)
    text = re.sub(r'(\*|_)(.*?)\1', r'\2', text)
    text = re.sub(r'~~(.*?)~~', r'\1', text)

    # 5. Minimalistyczne nagłówki
    text = re.sub(r'^\s*#{1,6}\s*', 'SECTION: ', text, flags=re.M)

    # 6. Usuń listy i blockquote
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.M)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.M)
    text = re.sub(r'^\s*>\s?', '', text, flags=re.M)

    # 7. Kompresja whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def compress_prompt2(text: str) -> str:
    """
    Lekki compressor promptu + próba naprawy JSON.
    Jeśli naprawa JSON się nie uda, zwraca dokładnie oryginalny tekst.
    
    UŻYCIE: Wyłącznie dla danych wejściowych od użytkownika lub API.
    NIE używać dla: wewnętrznych promptów systemowych, odpowiedzi AI,
    danych generowanych przez agenta.
    """
    original_text = text  # zachowaj oryginał

    if not text:
        return text

    try:
        # 1. Dekodowanie Unicode
        text = html.unescape(text)

        # 2. Markdown linki [text](url) → text (url)
        def replace_link(match):
            label = match.group(1)
            url = clean_url(match.group(2))
            return f"{label} ({url})"
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', replace_link, text)

        # 3. Usuwanie code block i inline code
        text = re.sub(r'```.*?```', '', text, flags=re.S)
        text = re.sub(r'`([^`]*)`', r'\1', text)

        # 4. Usuń markdown bold/italic/strike
        text = re.sub(r'(\*\*|__)(.*?)\1', r'\2', text)
        text = re.sub(r'(\*|_)(.*?)\1', r'\2', text)
        text = re.sub(r'~~(.*?)~~', r'\1', text)

        # 5. Minimalistyczne nagłówki
        text = re.sub(r'^\s*#{1,6}\s*', 'SECTION: ', text, flags=re.M)

        # 6. Usuń listy i blockquote
        text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.M)
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.M)
        text = re.sub(r'^\s*>\s?', '', text, flags=re.M)

        # 7. Kompresja whitespace
        text = re.sub(r'\s+', ' ', text).strip()
    

        # 8. Próba naprawy JSON
        try:
            json.loads(text)
        except json.JSONDecodeError:
            # prosta naprawa: escape cudzysłowy, usuń niepoprawne znaki
            text_safe = text.replace('\n', '\\n').replace('\t', '\\t')
            text_safe = text_safe.replace("'", '"')
            text_safe = re.sub(r',\s*([}\]])', r'\1', text_safe)  # usuń trailing comma
            json.loads(text_safe)  # jeśli się uda, text_safe jest OK
            text = text_safe

    except (json.JSONDecodeError, Exception):
        # jeśli naprawa JSON się nie uda → zwróć dokładnie oryginalny tekst
        return original_text

    return text


def estimate_compression_ratio(original: str, compressed: str) -> float:
    """
    Calculate the compression ratio between original and compressed text.
    
    Args:
        original: Original text
        compressed: Compressed text
        
    Returns:
        Compression ratio (0.0 to 1.0, where lower means more compression)
    """
    if not original:
        return 1.0
    return len(compressed) / len(original) if len(original) > 0 else 1.0


def estimate_token_savings(original: str, compressed: str) -> dict:
    """
    Estimate token savings from compression.
    
    Args:
        original: Original text
        compressed: Compressed text
        
    Returns:
        Dictionary with savings statistics
    """
    original_chars = len(original)
    compressed_chars = len(compressed)
    saved_chars = original_chars - compressed_chars
    
    # Rough estimate: ~4 characters per token
    original_tokens = max(1, original_chars // 4)
    compressed_tokens = max(1, compressed_chars // 4)
    saved_tokens = original_tokens - compressed_tokens
    
    return {
        'original_chars': original_chars,
        'compressed_chars': compressed_chars,
        'saved_chars': saved_chars,
        'original_tokens_est': original_tokens,
        'compressed_tokens_est': compressed_tokens,
        'saved_tokens_est': saved_tokens,
        'compression_ratio': estimate_compression_ratio(original, compressed)
    }