from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

from sessioniq.assistant import GroundedAssistant
from sessioniq.ingestion import ingest_file, supported_upload_types
from sessioniq.models import ProjectAsset, ProjectSummary, TaskStatus
from sessioniq.project_workspace import safe_upload_path, summarize_projects
from sessioniq.retrieval import InMemoryRetriever
from sessioniq.validation import validate_grounded_answer


def main() -> None:
    load_dotenv()
    st.set_page_config(page_title="SessionIQ", page_icon="SIQ", layout="wide")
    _ensure_state()

    st.title("SessionIQ")
    st.caption("Source-grounded AI assistant for music production sessions.")

    with st.sidebar:
        st.header("Session Sources")
        project_name = st.text_input(
            "Project / song",
            placeholder="e.g. Vivien remix, Album demos, Client cue 03",
        )
        upload_note = st.text_area("Session note", placeholder="Optional context for these uploads")
        uploads = st.file_uploader(
            "Upload audio, MIDI, or notes",
            type=supported_upload_types(),
            accept_multiple_files=True,
        )
        if st.button("Ingest uploads", type="primary", use_container_width=True):
            _ingest_uploads(uploads, upload_note, project_name)
        if st.button("Clear session", use_container_width=True):
            st.session_state.assets = []
            st.session_state.messages = []
            st.session_state.task_statuses = {}
            st.rerun()

    assets: list[ProjectAsset] = st.session_state.assets
    summaries = summarize_projects(assets, st.session_state.task_statuses)
    if assets:
        projects = ["All projects", *[summary.project_name for summary in summaries]]
        st.session_state.project_filter = st.selectbox(
            "Workspace",
            projects,
            index=projects.index(st.session_state.project_filter)
            if st.session_state.project_filter in projects
            else 0,
        )

    visible_assets = _filtered_assets(assets)
    visible_summaries = _filtered_summaries(summaries)
    overview_tab, files_tab, chat_tab = st.tabs(["Projects", "Files", "Ask"])

    with overview_tab:
        _render_project_board(visible_summaries)

    with files_tab:
        _render_assets(assets, visible_assets)

    with chat_tab:
        st.subheader("Ask the Session")
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        question = st.chat_input("Ask about tempo, notes, levels, tasks, or arrangement details")
        if question:
            _answer_question(question, assets)


def _ensure_state() -> None:
    st.session_state.setdefault("assets", [])
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("project_filter", "All projects")
    st.session_state.setdefault("task_statuses", {})


def _ingest_uploads(uploads: list | None, note: str, project_name: str) -> None:
    if not uploads:
        st.warning("Choose one or more files first.")
        return

    created: list[ProjectAsset] = []
    with st.spinner("Analyzing sources..."):
        for upload in uploads:
            saved_path = safe_upload_path(project_name, upload.name)
            saved_path.write_bytes(upload.getbuffer())
            try:
                created.append(
                    ingest_file(
                        saved_path,
                        note=note,
                        project_name=project_name,
                        stored_path=str(saved_path),
                    )
                )
            except Exception as exc:
                st.error(f"{upload.name}: {exc}")

    known_ids = {asset.id for asset in st.session_state.assets}
    st.session_state.assets.extend(asset for asset in created if asset.id not in known_ids)
    if created:
        st.success(f"Ingested {len(created)} source file(s).")


def _filtered_assets(assets: list[ProjectAsset]) -> list[ProjectAsset]:
    selected = st.session_state.get("project_filter", "All projects")
    if selected == "All projects":
        return assets
    return [asset for asset in assets if asset.project_name == selected]


def _filtered_summaries(summaries: list[ProjectSummary]) -> list[ProjectSummary]:
    selected = st.session_state.get("project_filter", "All projects")
    if selected == "All projects":
        return summaries
    return [summary for summary in summaries if summary.project_name == selected]


def _render_project_board(summaries: list[ProjectSummary]) -> None:
    st.subheader("Project Board")
    if not summaries:
        st.info("Upload files into a project to build the notebook.")
        return

    for summary in summaries:
        with st.container(border=True):
            st.markdown(f"### {summary.project_name}")
            metric_cols = st.columns(5)
            metric_cols[0].metric("Files", summary.asset_count)
            metric_cols[1].metric("Audio", summary.audio_count)
            metric_cols[2].metric("MIDI", summary.midi_count)
            metric_cols[3].metric("Notes", summary.note_count)
            metric_cols[4].metric("Tasks", len(summary.tasks))
            st.progress(summary.progress, text=f"{round(summary.progress * 100)}% complete")

            if not summary.tasks:
                st.caption(
                    "No action items found yet. Add notes like 'TODO', 'try', "
                    "'fix', or 'check'."
                )
                continue

            for task in summary.tasks:
                cols = st.columns([0.5, 0.24, 0.26])
                cols[0].markdown(f"{task.description}  \n`{task.source_file}`")
                status = cols[1].selectbox(
                    "Status",
                    [status.value for status in TaskStatus],
                    index=[status.value for status in TaskStatus].index(task.status.value),
                    key=f"task_status_{task.id}",
                    label_visibility="collapsed",
                )
                st.session_state.task_statuses[task.id] = status
                cols[2].caption(task.source_file)


def _render_assets(assets: list[ProjectAsset], visible_assets: list[ProjectAsset]) -> None:
    st.subheader("Assets")
    if not assets:
        st.info("Upload source files to begin.")
        return
    if not visible_assets:
        st.info("No files match the current workspace filter.")
        return

    st.dataframe(
        [_asset_row(asset) for asset in visible_assets],
        use_container_width=True,
        hide_index=True,
    )
    with st.expander("Metadata", expanded=False):
        selected = st.selectbox(
            "Inspect file",
            [asset.file_name for asset in visible_assets],
        )
        asset = next(item for item in visible_assets if item.file_name == selected)
        st.json(asset.compact_metadata())


def _answer_question(question: str, assets: list[ProjectAsset]) -> None:
    st.session_state.messages.append({"role": "user", "content": question})
    retriever = InMemoryRetriever()
    retriever.add_assets(assets)
    sources = retriever.search(question)
    answer = GroundedAssistant().answer(question, sources)
    errors = validate_grounded_answer(answer, sources)

    content = answer.answer
    if answer.citations:
        citations = "\n".join(
            f"- `{citation.file_name}`: {citation.evidence}" for citation in answer.citations
        )
        content = f"{content}\n\n**Sources**\n{citations}"
    if errors:
        content = f"{content}\n\n**Validation**\n" + "\n".join(f"- {error}" for error in errors)

    st.session_state.messages.append({"role": "assistant", "content": content})
    st.rerun()


def _asset_row(asset: ProjectAsset) -> dict[str, str | int | float | None]:
    row: dict[str, str | int | float | None] = {
        "Project": asset.project_name,
        "File": asset.file_name,
        "Type": asset.kind.value,
        "Duration": None,
        "BPM": None,
        "Notes": None,
    }
    if asset.audio:
        row["Duration"] = round(asset.audio.duration_seconds, 2)
        row["BPM"] = round(asset.audio.bpm_estimate, 1) if asset.audio.bpm_estimate else None
    if asset.midi:
        row["Duration"] = round(asset.midi.duration_seconds, 2)
        row["BPM"] = round(asset.midi.tempo_bpm, 1) if asset.midi.tempo_bpm else None
        row["Notes"] = asset.midi.note_count
    if asset.text:
        row["Notes"] = asset.text.word_count
    return row


if __name__ == "__main__":
    main()
