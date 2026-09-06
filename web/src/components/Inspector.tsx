import {
  FolderInput,
  Mic,
  Music4,
  RefreshCw,
  StickyNote,
  Trash2,
  Waves
} from "lucide-react";
import { lazy, Suspense, useState } from "react";

import { Badge, Button, Card, SectionTitle, Stat } from "./ui";
import { TagEditor } from "./shared";
import { typeTextColor, TypeIcon } from "./shared";
import { formatSeconds } from "../lib/utils";
import type { FileStatus, SessionAsset } from "../types";

const AnalysisCharts = lazy(() => import("./AnalysisCharts"));

const STATUS_TONE: Record<FileStatus, "neutral" | "green" | "amber" | "red" | "blue"> = {
  Idea: "neutral",
  "In Progress": "blue",
  "Needs Work": "amber",
  Ready: "green",
  Reference: "blue",
  Archived: "neutral"
};

export function Inspector({
  asset,
  accent,
  projectNames,
  onUpdate,
  onDelete,
  onSeek,
  onTranscribe,
  transcribingId,
  canTranscribe,
  onReanalyze,
  reanalyzingId
}: {
  asset?: SessionAsset;
  accent: string;
  projectNames: string[];
  onUpdate: (
    asset: SessionAsset,
    update: Partial<Pick<SessionAsset, "status" | "tags" | "project_name" | "note">>
  ) => Promise<boolean>;
  onDelete: (asset: SessionAsset) => void;
  onSeek: (assetId: string, time: number) => void;
  onTranscribe: (asset: SessionAsset) => void;
  transcribingId: string | null;
  canTranscribe: boolean;
  onReanalyze: (asset: SessionAsset) => void;
  reanalyzingId: string | null;
}) {
  if (!asset) {
    return (
      <Card className="p-4">
        <SectionTitle title="Inspector" />
        <EmptyInspector />
      </Card>
    );
  }
  const isAudio = asset.display_type === "Audio";
  const transcribing = transcribingId === asset.id;
  const reanalyzing = reanalyzingId === asset.id;
  return (
    <Card className="space-y-5 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <TypeIcon type={asset.display_type} />
            <h2 className="truncate text-base font-semibold tracking-tight">{asset.file_name}</h2>
          </div>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {asset.project_name} · <span className={typeTextColor(asset.display_type)}>{asset.display_type}</span>
            {asset.mode ? ` · ${asset.key ?? ""} ${asset.mode}`.replace("  ", " ") : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {asset.file_missing && (
            <Badge tone="red" title="The stored file is gone; playback will fail until it is restored or re-uploaded.">
              File missing
            </Badge>
          )}
          <Badge tone={STATUS_TONE[asset.status]}>{asset.status}</Badge>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => onDelete(asset)}
            aria-label="Delete file"
            title="Delete file"
            className="text-muted-foreground hover:text-danger"
          >
            <Trash2 className="size-4" />
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <FolderInput className="size-3.5" /> Move to
        </label>
        <select
          className="select-compact"
          value={asset.project_name}
          onChange={(event) => onUpdate(asset, { project_name: event.target.value })}
        >
          {Array.from(new Set([asset.project_name, "Unassigned", ...projectNames])).map((name) => (
            <option key={name}>{name}</option>
          ))}
        </select>
      </div>

      <TagEditor tags={asset.tags} onChange={(tags) => onUpdate(asset, { tags })} />

      {asset.media_url && asset.display_type === "Image" && (
        <img
          src={asset.media_url}
          alt={asset.file_name}
          className="max-h-72 w-full rounded-md border border-border object-contain"
        />
      )}

      <NotesEditor key={asset.id} asset={asset} onSave={(note) => onUpdate(asset, { note })} />

      {asset.audio?.codec && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="Codec" value={asset.audio.codec} />
          <Stat label="Peak dB" value={asset.audio.peak_db?.toFixed(1) ?? "—"} />
          <Stat label="RMS dB" value={asset.audio.rms_db?.toFixed(1) ?? "—"} />
          <Stat label="LUFS" value={asset.audio.integrated_lufs?.toFixed(1) ?? "—"} hint="Integrated loudness (ITU-R BS.1770-4)" />
          <Stat label="Brightness" value={asset.audio.spectral_centroid_mean?.toFixed(0) ?? "—"} />
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {isAudio && asset.energy_peak_seconds != null && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => onSeek(asset.id, asset.energy_peak_seconds!)}
            title="Jump the player to the loudest section"
          >
            <Waves className="size-4" /> Loudest moment · {formatSeconds(asset.energy_peak_seconds)}
          </Button>
        )}
        {isAudio && asset.first_beat_seconds != null && asset.first_beat_seconds > 0.5 && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => onSeek(asset.id, asset.first_beat_seconds!)}
            title="Play from the first detected beat"
          >
            <Music4 className="size-4" /> First beat · {formatSeconds(asset.first_beat_seconds)}
          </Button>
        )}
        {isAudio && canTranscribe && !asset.file_missing && (
          <Button
            size="sm"
            variant="outline"
            disabled={transcribing}
            onClick={() => onTranscribe(asset)}
            title="Transcribe speech in this file into a note with local Whisper"
          >
            <Mic className="size-4" /> {transcribing ? "Transcribing…" : "Transcribe voice memo"}
          </Button>
        )}
        {asset.last_analyzed && !asset.file_missing && (
          <Button
            size="sm"
            variant="outline"
            disabled={reanalyzing}
            onClick={() => onReanalyze(asset)}
            title="Re-run analysis on the stored file — keeps status, tags, and notes, and upgrades older analysis fields"
          >
            <RefreshCw className={reanalyzing ? "size-4 animate-spin" : "size-4"} />
            {reanalyzing ? "Re-analyzing…" : "Re-analyze"}
          </Button>
        )}
      </div>

      {(asset.audio || asset.midi) && <AnalysisSection asset={asset} accent={accent} />}

    </Card>
  );
}

function EmptyInspector() {
  return (
    <div className="mt-4 rounded-md border border-dashed border-border bg-muted/30 px-4 py-10 text-center text-sm text-muted-foreground">
      Select or upload a file to inspect its analysis.
    </div>
  );
}

function AnalysisSection({ asset, accent }: { asset: SessionAsset; accent: string }) {
  const [open, setOpen] = useState(false);
  return <details onToggle={event => setOpen(event.currentTarget.open)}>
    <summary className="cursor-pointer text-sm font-medium">Audio & MIDI analysis</summary>
    {open && <Suspense fallback={<p role="status" className="p-3 text-sm text-muted-foreground">Loading charts…</p>}><AnalysisCharts asset={asset} accent={accent} /></Suspense>}
  </details>;
}

function NotesEditor({ asset, onSave }: { asset: SessionAsset; onSave: (note: string) => Promise<boolean> }) {
  const storageKey = `sessioniq-draft:${asset.id}`;
  const [note, setNote] = useState(() => {
    try { return localStorage.getItem(storageKey) ?? asset.note ?? ""; }
    catch { return asset.note ?? ""; }
  });
  const [saving, setSaving] = useState(false);
  const dirty = note !== (asset.note ?? "");
  async function save() {
    if (saving) return;
    setSaving(true);
    if (await onSave(note)) {
      try { localStorage.removeItem(storageKey); } catch { /* Storage can be disabled. */ }
    }
    setSaving(false);
  }
  return <div>
    <div className="mb-2 flex items-center justify-between gap-2">
      <h3 className="flex items-center gap-1.5 text-sm font-medium"><StickyNote className="size-4" /> Notes</h3>
      {dirty && <Button variant="soft" size="sm" disabled={saving} onClick={() => void save()}>{saving ? "Saving…" : "Save notes"}</Button>}
    </div>
    <textarea aria-label={`Notes for ${asset.file_name}`} className="input min-h-24 resize-y" value={note}
      placeholder="Mix notes, ideas, to-dos… Ctrl+Enter to save."
      onKeyDown={event => { if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) { event.preventDefault(); void save(); } }}
      onChange={event => {
        setNote(event.target.value);
        try { localStorage.setItem(storageKey, event.target.value); } catch { /* Keep the in-memory draft. */ }
      }} />
    {dirty && <p className="mt-1 text-xs text-warning">Unsaved changes — save to update tasks and assistant context.</p>}
  </div>;
}
