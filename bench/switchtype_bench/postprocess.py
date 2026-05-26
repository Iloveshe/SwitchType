from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class HotwordConfig:
    protected_terms: list[str]
    replacements: dict[str, str]


class PostProcessor:
    def __init__(self, config: HotwordConfig):
        self.config = config

    def process(self, text: str) -> str:
        output = text.strip()
        for source, target in self.config.replacements.items():
            output = output.replace(source, target)
        output = re.sub(r"\s+", " ", output)
        for term in self.config.protected_terms:
            output = self._normalize_spaced_acronym(output, term)
            output = self._space_ascii_term(output, term)
        return output.strip()

    def _normalize_spaced_acronym(self, text: str, term: str) -> str:
        if not term or not term.isascii() or not term.isupper() or not term.isalpha() or len(term) < 2:
            return text
        pattern = r"\b" + r"\s+".join(re.escape(character) for character in term) + r"\b"
        return re.sub(pattern, term, text, flags=re.IGNORECASE)

    def _space_ascii_term(self, text: str, term: str) -> str:
        if not term or not term.isascii():
            return text
        escaped = re.escape(term)
        text = re.sub(rf"([\u4e00-\u9fff])({escaped})", r"\1 \2", text)
        text = re.sub(rf"({escaped})([\u4e00-\u9fff])", r"\1 \2", text)
        return re.sub(r"\s+", " ", text)
