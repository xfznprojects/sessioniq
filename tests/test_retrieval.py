from __future__ import annotations

from sessioniq.models import AssetKind, AudioMetadata, NoteMetadata, ProjectAsset
from sessioniq.retrieval import VECTOR_DISABLE_ENV, HybridRetriever, InMemoryRetriever


def test_retrieval_matches_bpm_metadata():
    asset = ProjectAsset(
        id="breakbeat",
        file_name="breakbeat.wav",
        kind=AssetKind.AUDIO,
        audio=AudioMetadata(
            duration_seconds=8,
            bpm_estimate=124,
            sample_rate=44_100,
            peak_amplitude=0.8,
            rms_amplitude=0.2,
        ),
    )
    retriever = InMemoryRetriever()
    retriever.add_assets([asset])

    results = retriever.search("Which file is around 123 bpm?")

    assert results
    assert results[0].asset.file_name == "breakbeat.wav"


def test_retrieval_matches_production_note_text():
    asset = ProjectAsset(
        id="notes",
        file_name="todo.md",
        kind=AssetKind.NOTE,
        text=NoteMetadata(text="Todo: automate filter sweep before the chorus.", word_count=7),
    )
    retriever = InMemoryRetriever()
    retriever.add_assets([asset])

    results = retriever.search("what todo mentions chorus")

    assert results
    assert results[0].asset.file_name == "todo.md"


def test_retrieval_expands_loudness_synonyms():
    asset = ProjectAsset(
        id="mix",
        file_name="mix.wav",
        kind=AssetKind.AUDIO,
        audio=AudioMetadata(
            duration_seconds=8,
            sample_rate=44_100,
            peak_amplitude=0.9,
            rms_amplitude=0.3,
            peak_db=-1.0,
            rms_db=-10.5,
        ),
    )
    retriever = InMemoryRetriever()
    retriever.add_assets([asset])

    results = retriever.search("which song is the loudest?")

    assert results
    assert results[0].asset.file_name == "mix.wav"
    assert results[0].score > 0


def test_aggregate_query_returns_all_assets():
    assets = [
        ProjectAsset(
            id=f"clip-{index}",
            file_name=f"clip-{index}.wav",
            kind=AssetKind.AUDIO,
            audio=AudioMetadata(duration_seconds=8, sample_rate=44_100, bpm_estimate=100 + index),
        )
        for index in range(6)
    ]
    retriever = InMemoryRetriever()
    retriever.add_assets(assets)

    results = retriever.search("list all files")

    assert len(results) == 6


def test_unmatched_query_falls_back_to_recent_assets():
    asset = ProjectAsset(
        id="drums",
        file_name="drums.wav",
        kind=AssetKind.AUDIO,
        last_analyzed="2026-07-08T00:00:00+00:00",
        audio=AudioMetadata(duration_seconds=8, sample_rate=44_100),
    )
    retriever = InMemoryRetriever()
    retriever.add_assets([asset])

    results = retriever.search("qwxyz nonsense")

    assert results
    assert results[0].asset.file_name == "drums.wav"


def test_search_filters_by_project_name():
    assets = [
        ProjectAsset(
            id="remix-drums",
            file_name="drums.wav",
            kind=AssetKind.AUDIO,
            project_name="Remix",
            audio=AudioMetadata(duration_seconds=8, sample_rate=44_100, bpm_estimate=120),
        ),
        ProjectAsset(
            id="album-drums",
            file_name="album-drums.wav",
            kind=AssetKind.AUDIO,
            project_name="Album",
            audio=AudioMetadata(duration_seconds=8, sample_rate=44_100, bpm_estimate=120),
        ),
    ]
    retriever = InMemoryRetriever()
    retriever.add_assets(assets)

    results = retriever.search("list all audio files", project_name="Remix")

    assert [source.asset.id for source in results] == ["remix-drums"]


def test_hybrid_retriever_degrades_to_lexical(monkeypatch):
    monkeypatch.setenv(VECTOR_DISABLE_ENV, "1")
    asset = ProjectAsset(
        id="lex",
        file_name="lex.wav",
        kind=AssetKind.AUDIO,
        audio=AudioMetadata(duration_seconds=8, sample_rate=44_100, bpm_estimate=95),
    )
    retriever = HybridRetriever(persist_directory="unused")
    retriever.add_assets([asset])

    assert retriever.vector_enabled is False
    results = retriever.search("which file is around 95 bpm?")
    assert results
    assert results[0].asset.file_name == "lex.wav"


def test_retrieval_matches_project_name():
    asset = ProjectAsset(
        id="vivien-stems",
        file_name="drums.wav",
        kind=AssetKind.AUDIO,
        project_name="Vivien remix",
        audio=AudioMetadata(duration_seconds=8, sample_rate=44_100),
    )
    retriever = InMemoryRetriever()
    retriever.add_assets([asset])

    results = retriever.search("show me files for vivien")

    assert results
    assert results[0].asset.file_name == "drums.wav"
