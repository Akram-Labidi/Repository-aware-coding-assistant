"""Okapi BM25 implementation optimized for source code retrieval.

Includes a code-aware subword tokenizer that handles snake_case, camelCase,
PascalCase, and preserves programming identifiers.
"""

from __future__ import annotations
import math
import re
from collections import Counter
from typing import Dict, List, Optional, Set, Tuple


class CodeTokenizer:
    """Tokenizer specifically tuned for source code and technical documentation."""

    SPLIT_REGEX = re.compile(r"[^a-zA-Z0-9_]")
    CAMEL_SPLIT = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

    STOPWORDS: Set[str] = {
        "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "with",
        "by", "from", "up", "about", "into", "over", "after", "is", "are", "was",
        "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
        "but", "if", "then", "else", "when", "where", "why", "how", "all", "any",
        "both", "each", "few", "more", "most", "other", "some", "such", "no",
        "nor", "not", "only", "own", "same", "so", "than", "too", "very", "can",
        "will", "just", "should", "now"
    }

    @classmethod
    def tokenize(cls, text: str, min_len: int = 2) -> List[str]:
        if not text:
            return []

        tokens: List[str] = []
        raw_words = cls.SPLIT_REGEX.split(text)

        for word in raw_words:
            if not word or len(word) < min_len:
                continue

            low_word = word.lower()
            if low_word in cls.STOPWORDS:
                continue

            # Add original lowercase word
            tokens.append(low_word)

            # Handle snake_case
            if "_" in word:
                parts = word.split("_")
                for p in parts:
                    if len(p) >= min_len and p.lower() not in cls.STOPWORDS:
                        tokens.append(p.lower())
                        camel_sub = cls.CAMEL_SPLIT.split(p)
                        if len(camel_sub) > 1:
                            for cs in camel_sub:
                                if len(cs) >= min_len and cs.lower() not in cls.STOPWORDS:
                                    tokens.append(cs.lower())

            # Handle camelCase & PascalCase
            camel_parts = cls.CAMEL_SPLIT.split(word)
            if len(camel_parts) > 1:
                for cp in camel_parts:
                    if len(cp) >= min_len and cp.lower() not in cls.STOPWORDS:
                        tokens.append(cp.lower())

        return tokens


class BM25Index:
    """Okapi BM25 Index with persistence capability."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_ids: List[str] = []
        self.doc_lengths: List[int] = []
        self.doc_len_lookup: Dict[str, int] = {}
        self.avg_doc_len: float = 0.0
        self.total_docs: int = 0
        # Inverted index: token -> {doc_id: term_frequency}
        self.inverted_index: Dict[str, Dict[str, int]] = {}
        # Document frequency: token -> count of docs containing token
        self.doc_freq: Dict[str, int] = {}

    def index_documents(self, documents: Dict[str, str]) -> None:
        """Indexes a dictionary of {doc_id: document_text}."""
        self.doc_ids = []
        self.doc_lengths = []
        self.doc_len_lookup = {}
        self.inverted_index = {}
        self.doc_freq = {}

        total_tokens = 0

        for doc_id, text in documents.items():
            tokens = CodeTokenizer.tokenize(text)
            doc_len = len(tokens)
            self.doc_ids.append(doc_id)
            self.doc_lengths.append(doc_len)
            self.doc_len_lookup[doc_id] = doc_len
            total_tokens += doc_len

            term_counts = Counter(tokens)
            for token, count in term_counts.items():
                if token not in self.inverted_index:
                    self.inverted_index[token] = {}
                    self.doc_freq[token] = 0
                self.inverted_index[token][doc_id] = count
                self.doc_freq[token] += 1

        self.total_docs = len(self.doc_ids)
        self.avg_doc_len = (total_tokens / self.total_docs) if self.total_docs > 0 else 0.0

    def add_document(self, doc_id: str, text: str) -> None:
        """Incrementally indexes a single document."""
        if doc_id in self.doc_len_lookup:
            self.remove_document(doc_id)

        tokens = CodeTokenizer.tokenize(text)
        doc_len = len(tokens)
        self.doc_ids.append(doc_id)
        self.doc_lengths.append(doc_len)
        self.doc_len_lookup[doc_id] = doc_len

        term_counts = Counter(tokens)
        for token, count in term_counts.items():
            if token not in self.inverted_index:
                self.inverted_index[token] = {}
                self.doc_freq[token] = 0
            self.inverted_index[token][doc_id] = count
            self.doc_freq[token] += 1

        self.total_docs = len(self.doc_ids)
        self.avg_doc_len = (sum(self.doc_lengths) / self.total_docs) if self.total_docs > 0 else 0.0

    def remove_document(self, doc_id: str) -> None:
        """Removes a document from the index."""
        if doc_id not in self.doc_len_lookup:
            return

        old_len = self.doc_len_lookup.pop(doc_id)
        if doc_id in self.doc_ids:
            self.doc_ids.remove(doc_id)
        if old_len in self.doc_lengths:
            self.doc_lengths.remove(old_len)

        for token in list(self.inverted_index.keys()):
            if doc_id in self.inverted_index[token]:
                del self.inverted_index[token][doc_id]
                self.doc_freq[token] -= 1
                if self.doc_freq[token] <= 0:
                    del self.inverted_index[token]
                    del self.doc_freq[token]

        self.total_docs = len(self.doc_ids)
        self.avg_doc_len = (sum(self.doc_lengths) / self.total_docs) if self.total_docs > 0 else 0.0

    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """Scores documents matching query and returns list of (doc_id, bm25_score)."""
        if self.total_docs == 0:
            return []

        query_tokens = CodeTokenizer.tokenize(query)
        if not query_tokens:
            return []

        scores: Dict[str, float] = {}

        for token in query_tokens:
            if token not in self.inverted_index:
                continue

            df = self.doc_freq[token]
            # Okapi BM25 Robertson-Spärck Jones IDF with smoothing
            idf = math.log(((self.total_docs - df + 0.5) / (df + 0.5)) + 1.0)
            if idf <= 0:
                idf = 0.01

            for doc_id, tf in self.inverted_index[token].items():
                doc_len = self.doc_len_lookup.get(doc_id, self.avg_doc_len)
                denom = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / (self.avg_doc_len or 1.0)))
                score = idf * ((tf * (self.k1 + 1.0)) / denom)
                scores[doc_id] = scores.get(doc_id, 0.0) + score

        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_results[:top_k]

    def to_dict(self) -> Dict:
        return {
            "k1": self.k1,
            "b": self.b,
            "doc_len_lookup": self.doc_len_lookup,
            "avg_doc_len": self.avg_doc_len,
            "total_docs": self.total_docs,
            "inverted_index": self.inverted_index,
            "doc_freq": self.doc_freq,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> BM25Index:
        idx = cls(k1=data.get("k1", 1.5), b=data.get("b", 0.75))
        idx.doc_len_lookup = data.get("doc_len_lookup", {})
        idx.doc_ids = list(idx.doc_len_lookup.keys())
        idx.doc_lengths = list(idx.doc_len_lookup.values())
        idx.avg_doc_len = data.get("avg_doc_len", 0.0)
        idx.total_docs = data.get("total_docs", 0)
        idx.inverted_index = data.get("inverted_index", {})
        idx.doc_freq = data.get("doc_freq", {})
        return idx
