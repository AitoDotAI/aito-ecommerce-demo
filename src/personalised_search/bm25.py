"""A plain Okapi BM25 over the product names, in Python (ADR 0037 §3).

It is the reference for Smart Search's left column, `_search products`
ordered by `$similarity` over the name: if the two agree, that column is a
standard BM25 and the page may call it one. If they don't, the page calls
it "Aito's text similarity" instead (`probe.py` decides, before the run).

The textbook form, with Lucene's non-negative IDF:

    score(q, d) = Σ_t∈q  idf(t) · tf(t,d) · (k1 + 1) / (tf(t,d) + k1 · (1 − b + b · |d| / avgdl))
    idf(t)      = ln(1 + (N − df(t) + 0.5) / (df(t) + 0.5))
"""

from __future__ import annotations

import math
import re
from collections import Counter

K1 = 1.2
B = 0.75


def tokens(text: str) -> list[str]:
    """Lower-cased runs of letters and digits: "Grain-Free 2kg" → ["grain", "free", "2kg"]."""
    return re.findall(r"[a-z0-9]+", text.lower())


class Bm25:
    def __init__(self, documents: dict[str, str], k1: float = K1, b: float = B) -> None:
        self.k1, self.b = k1, b
        self.terms = {doc_id: Counter(tokens(text)) for doc_id, text in documents.items()}
        self.length = {doc_id: sum(tf.values()) for doc_id, tf in self.terms.items()}
        self.average_length = sum(self.length.values()) / len(self.length)
        df: Counter[str] = Counter()
        for tf in self.terms.values():
            df.update(tf.keys())
        n = len(self.terms)
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def score(self, query: str, doc_id: str) -> float:
        tf, length = self.terms[doc_id], self.length[doc_id]
        norm = self.k1 * (1 - self.b + self.b * length / self.average_length)
        return sum(self.idf[t] * tf[t] * (self.k1 + 1) / (tf[t] + norm)
                   for t in tokens(query) if tf[t])

    def ranked(self, query: str) -> list[str]:
        """Documents holding at least one query word, best first; ties by id."""
        scored = [(self.score(query, d), d) for d in self.terms]
        return [d for s, d in sorted(scored, key=lambda x: (-x[0], x[1])) if s > 0]
