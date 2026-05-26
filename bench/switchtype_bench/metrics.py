from __future__ import annotations

import re
from typing import Iterable


def edit_distance(left: list[str], right: list[str]) -> int:
    previous = list(range(len(right) + 1))
    for i, left_item in enumerate(left, start=1):
        current = [i]
        for j, right_item in enumerate(right, start=1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (0 if left_item == right_item else 1)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


def char_error_rate(reference: str, hypothesis: str) -> float:
    reference_chars = [char for char in reference if not char.isspace()]
    hypothesis_chars = [char for char in hypothesis if not char.isspace()]
    if not reference_chars:
        return 0.0 if not hypothesis_chars else 1.0
    return edit_distance(reference_chars, hypothesis_chars) / len(reference_chars)


def _word_tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_+.-]+|[\u4e00-\u9fff]", text)


def word_error_rate(reference: str, hypothesis: str) -> float:
    reference_words = _word_tokens(reference)
    hypothesis_words = _word_tokens(hypothesis)
    if not reference_words:
        return 0.0 if not hypothesis_words else 1.0
    return edit_distance(reference_words, hypothesis_words) / len(reference_words)


def technical_term_accuracy(terms: Iterable[str], hypothesis: str) -> dict[str, float | int]:
    unique_terms = list(dict.fromkeys(terms))
    if not unique_terms:
        return {"matched": 0, "total": 0, "accuracy": 1.0}
    matched = sum(1 for term in unique_terms if term in hypothesis)
    return {"matched": matched, "total": len(unique_terms), "accuracy": matched / len(unique_terms)}
