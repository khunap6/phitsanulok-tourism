"""
preprocessor.py — Thai text preprocessing with PyThaiNLP
Step A of the NLP pipeline: tokenize, remove noise, return clean tokens
"""

import re
from functools import lru_cache

from pythainlp import word_tokenize
from pythainlp.corpus.common import thai_stopwords

_STOP_WORDS: frozenset[str] = frozenset(thai_stopwords())

_NOISE_PATTERN = re.compile(
    r"http\S+|www\.\S+"           # URLs
    r"|<[^>]+>"                   # HTML tags
    r"|[\U00010000-\U0010ffff]"   # emoji (surrogate range)
    r"|[\U0001F300-\U0001FAFF]"   # emoji (main range)
    r"|[^฀-๿\w\s]",     # non-Thai non-ASCII non-space
    re.UNICODE,
)


def clean_text(text: str) -> str:
    """Remove URLs, HTML, emoji, and special characters."""
    text = _NOISE_PATTERN.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def preprocess(text: str) -> tuple[str, list[str]]:
    """
    Full preprocessing pipeline.

    Returns:
        cleaned_text: joined filtered tokens
        tokens: filtered token list
    """
    cleaned = clean_text(text)

    raw_tokens = word_tokenize(cleaned, engine="newmm", keep_whitespace=False)

    tokens = [
        tok for tok in raw_tokens
        if len(tok) >= 2
        and tok not in _STOP_WORDS
        and not tok.isspace()
    ]

    return " ".join(tokens), tokens
