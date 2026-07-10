from __future__ import annotations

import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Protocol

from sessioniq.models import ProjectAsset, RetrievedSource

TOKEN_RE = re.compile(r"[a-zA-Z0-9_.#-]+")

VECTOR_DISABLE_ENV = "SESSIONIQ_DISABLE_VECTOR"

STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "do",
        "does", "for", "from", "has", "have", "how", "i", "in", "is", "it",
        "its", "me", "my", "of", "on", "or", "our", "should", "that", "the",
        "their", "them", "there", "these", "this", "to", "was", "we", "what",
        "when", "which", "who", "will", "with", "you", "your",
    }
)

# Query-intent synonyms: map natural-language words to the vocabulary that
# actually appears in extracted metadata, so questions like "which song is
# loudest" can reach assets whose search text only says "peak" and "rms".
SYNONYMS: dict[str, tuple[str, ...]] = {
    "loud": ("peak", "rms", "db", "level", "loudness"),
    "loudest": ("peak", "rms", "db", "level"),
    "quiet": ("peak", "rms", "db", "level"),
    "quietest": ("peak", "rms", "db", "level"),
    "volume": ("peak", "rms", "db", "level"),
    "tempo": ("bpm",),
    "fast": ("bpm", "tempo"),
    "fastest": ("bpm", "tempo"),
    "slow": ("bpm", "tempo"),
    "slowest": ("bpm", "tempo"),
    "speed": ("bpm", "tempo"),
    "song": ("audio", "file", "track"),
    "songs": ("audio", "file", "track"),
    "track": ("audio", "file"),
    "tracks": ("audio", "file"),
    "tune": ("audio", "file"),
    "music": ("audio", "midi"),
    "recording": ("audio",),
    "beat": ("bpm", "audio"),
    "todo": ("task", "action", "note"),
    "todos": ("task", "action", "note"),
    "task": ("action", "note", "todo"),
    "tasks": ("action", "note", "todo"),
    "unfinished": ("task", "action", "needs", "work"),
    "instrument": ("midi", "instruments"),
    "melody": ("midi", "notes"),
    "chords": ("midi", "notes", "chord"),
    "long": ("duration",),
    "longest": ("duration",),
    "short": ("duration",),
    "shortest": ("duration",),
    "length": ("duration",),
    "bright": ("brightness", "centroid"),
    "brightness": ("centroid",),
    "key": ("key",),
}

# Words that signal the question is about the whole library rather than one
# file, so retrieval should hand the assistant every candidate.
AGGREGATE_HINTS = frozenset(
    {
        "all", "any", "average", "compare", "count", "each", "every",
        "everything", "fastest", "highest", "how", "largest", "list",
        "longest", "loudest", "lowest", "many", "most", "overview",
        "quietest", "ready", "shortest", "slowest", "smallest", "status",
        "summarize", "summary", "total", "which",
    }
)


class Retriever(Protocol):
    def add_assets(self, assets: list[ProjectAsset]) -> None: ...

    def search(
        self,
        query: str,
        limit: int = 4,
        project_name: str | None = None,
    ) -> list[RetrievedSource]: ...


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def content_tokens(text: str) -> list[str]:
    return [token for token in tokenize(text) if token not in STOPWORDS]


def expand_query_tokens(tokens: list[str]) -> Counter[str]:
    """Weight original query tokens fully and synonym expansions at half."""
    weighted: Counter[str] = Counter()
    for token in tokens:
        weighted[token] += 1.0
        for synonym in SYNONYMS.get(token, ()):
            weighted[synonym] = max(weighted[synonym], 0.5)
    return weighted


def is_aggregate_query(query: str) -> bool:
    return bool(set(tokenize(query)) & AGGREGATE_HINTS)


class InMemoryRetriever:
    """Lexical retrieval over extracted metadata: synonym expansion plus IDF cosine."""

    def __init__(self) -> None:
        self.assets: list[ProjectAsset] = []

    def add_assets(self, assets: list[ProjectAsset]) -> None:
        known_ids = {asset.id for asset in self.assets}
        self.assets.extend(asset for asset in assets if asset.id not in known_ids)

    def remove_asset(self, asset_id: str) -> None:
        self.assets = [asset for asset in self.assets if asset.id != asset_id]

    def search(
        self,
        query: str,
        limit: int = 4,
        project_name: str | None = None,
    ) -> list[RetrievedSource]:
        candidates = [
            asset
            for asset in self.assets
            if project_name is None
            or asset.project_name == project_name
            or asset.project_name.startswith(project_name + "/")
        ]
        if not candidates:
            return []

        if is_aggregate_query(query):
            limit = max(limit, len(candidates))

        query_counts = expand_query_tokens(content_tokens(query))
        doc_counts = {
            asset.id: Counter(content_tokens(asset.search_text())) for asset in candidates
        }
        idf = _inverse_document_frequency(doc_counts.values())
        semantic = self._semantic_scores(query, candidates)

        scored: list[RetrievedSource] = []
        for asset in candidates:
            lexical_score = _weighted_cosine(query_counts, doc_counts[asset.id], idf)
            metadata_score = _metadata_score(query, asset)
            score = lexical_score + metadata_score + semantic.get(asset.id, 0.0)
            if score > 0:
                scored.append(RetrievedSource(asset=asset, score=score))

        ranked = sorted(scored, key=lambda item: item.score, reverse=True)[:limit]
        if ranked:
            return ranked

        # Nothing matched, but the library is not empty: fall back to the most
        # recently analyzed assets so the assistant can still ground an answer
        # instead of claiming it knows nothing.
        recent = sorted(
            candidates,
            key=lambda asset: asset.last_analyzed or "",
            reverse=True,
        )[:limit]
        return [RetrievedSource(asset=asset, score=0.0) for asset in recent]

    def _semantic_scores(
        self,
        query: str,
        candidates: list[ProjectAsset],
    ) -> dict[str, float]:
        """Hook for subclasses that can score semantic similarity."""
        return {}


class HybridRetriever(InMemoryRetriever):
    """Lexical retrieval blended with ChromaDB vector similarity.

    The vector layer is strictly optional: if chromadb is not installed, the
    embedding model cannot be downloaded, or SESSIONIQ_DISABLE_VECTOR is set,
    search silently degrades to pure lexical scoring. Chroma stores its index
    under the given persist directory and downloads its small embedding model
    to the user cache on first use; neither belongs in the repository.
    """

    def __init__(
        self,
        persist_directory: str | Path = "data/chroma",
        collection_name: str = "assets",
    ) -> None:
        super().__init__()
        self._collection = None
        if os.getenv(VECTOR_DISABLE_ENV):
            return
        try:
            import chromadb

            client = chromadb.PersistentClient(path=str(persist_directory))
            self._collection = client.get_or_create_collection(name=collection_name)
        except Exception:
            self._collection = None

    @property
    def vector_enabled(self) -> bool:
        return self._collection is not None

    def add_assets(self, assets: list[ProjectAsset]) -> None:
        known_ids = {asset.id for asset in self.assets}
        fresh = [asset for asset in assets if asset.id not in known_ids]
        super().add_assets(assets)
        if not fresh or self._collection is None:
            return
        try:
            self._collection.upsert(
                ids=[asset.id for asset in fresh],
                documents=[asset.search_text() for asset in fresh],
                metadatas=[
                    {
                        "file_name": asset.file_name,
                        "kind": asset.kind.value,
                        "project_name": asset.project_name,
                    }
                    for asset in fresh
                ],
            )
        except Exception:
            # Typically a failed embedding-model download on first use.
            self._collection = None

    def remove_asset(self, asset_id: str) -> None:
        super().remove_asset(asset_id)
        if self._collection is None:
            return
        try:
            self._collection.delete(ids=[asset_id])
        except Exception:
            self._collection = None

    def refresh_asset(self, asset: ProjectAsset) -> None:
        """Re-embed one asset after its metadata (status, tags) changed."""
        if self._collection is None:
            return
        try:
            self._collection.upsert(
                ids=[asset.id],
                documents=[asset.search_text()],
                metadatas=[
                    {
                        "file_name": asset.file_name,
                        "kind": asset.kind.value,
                        "project_name": asset.project_name,
                    }
                ],
            )
        except Exception:
            self._collection = None

    def _semantic_scores(
        self,
        query: str,
        candidates: list[ProjectAsset],
    ) -> dict[str, float]:
        if self._collection is None or not candidates:
            return {}
        try:
            result = self._collection.query(
                query_texts=[query],
                n_results=min(max(len(self.assets), 1), 50),
            )
        except Exception:
            self._collection = None
            return {}
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        candidate_ids = {asset.id for asset in candidates}
        return {
            asset_id: 1.0 / (1.0 + float(distance))
            for asset_id, distance in zip(ids, distances, strict=False)
            if asset_id in candidate_ids
        }


def _inverse_document_frequency(documents) -> dict[str, float]:
    document_list = list(documents)
    total = len(document_list)
    if not total:
        return {}
    frequency: Counter[str] = Counter()
    for counts in document_list:
        frequency.update(set(counts))
    return {
        token: 1.0 + math.log(total / count)
        for token, count in frequency.items()
    }


def _weighted_cosine(
    query: Counter[str],
    document: Counter[str],
    idf: dict[str, float],
) -> float:
    if not query or not document:
        return 0.0
    overlap = set(query) & set(document)
    if not overlap:
        return 0.0
    numerator = sum(query[token] * document[token] * idf.get(token, 1.0) for token in overlap)
    query_norm = math.sqrt(sum(value * value for value in query.values()))
    doc_norm = math.sqrt(
        sum((count * idf.get(token, 1.0)) ** 2 for token, count in document.items())
    )
    return numerator / (query_norm * doc_norm) if query_norm and doc_norm else 0.0


def _metadata_score(query: str, asset: ProjectAsset) -> float:
    score = 0.0
    query_lower = query.lower()
    query_tokens = set(tokenize(query_lower))
    numbers = [float(match) for match in re.findall(r"\d+(?:\.\d+)?", query)]

    if asset.audio and asset.audio.bpm_estimate:
        for number in numbers:
            if abs(asset.audio.bpm_estimate - number) <= 2:
                score += 1.5

    if asset.project_name != "Unassigned":
        project_tokens = set(tokenize(asset.project_name))
        if project_tokens & query_tokens:
            score += 0.6

    file_tokens = set(content_tokens(Path(asset.file_name).stem.replace("_", " ")))
    if file_tokens & query_tokens:
        score += 0.8

    if asset.midi and any(word in query_lower for word in ["midi", "note", "chord", "velocity"]):
        score += 0.4

    if asset.text and any(word in query_lower for word in ["todo", "task", "unfinished", "note"]):
        score += 0.4

    if asset.audio and any(
        word in query_lower
        for word in ["audio", "song", "track", "loud", "bpm", "tempo", "mix", "master"]
    ):
        score += 0.2

    asset_key = (
        asset.audio.key_estimate
        if asset.audio
        else asset.midi.key_estimate
        if asset.midi
        else None
    )
    if asset_key and "key" in query_tokens:
        score += 0.3
        key_pattern = rf"\b{re.escape(asset_key.lower())}\b"
        if re.search(key_pattern, query_lower):
            score += 0.7

    status_phrase = asset.status.value.lower()
    if status_phrase in query_lower:
        score += 0.5

    return score
