import { Brain, CalendarClock, FileAudio, FileText, Music4, Plus, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge, Button, Card, SectionTitle, Stat } from "./ui";
import type { SessionAsset } from "../types";

export function StudioView({ assets }: { assets: SessionAsset[] }) {
  return (
    <div className="space-y-6">
      <AIMemory />
      <SessionTimeline assets={assets} />
    </div>
  );
}

function AIMemory() {
  const [memory, setMemory] = useState<any>(null);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    fetch("/api/memory").then((r) => r.json()).then(setMemory).catch(() => setMemory(null));
  }, []);

  async function save(preferences: string[]) {
    const updated = await (
      await fetch("/api/memory", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preferences })
      })
    ).json();
    setMemory(updated);
  }

  if (!memory) {
    return (
      <Card className="p-4">
        <SectionTitle icon={<Brain className="size-5" />} title="AI Memory" subtitle="Loading…" />
      </Card>
    );
  }

  const prefs: string[] = memory.preferences ?? [];

  return (
    <Card className="p-4">
      <SectionTitle
        icon={<Brain className="size-5" />}
        title="AI Memory"
        subtitle="Your creative fingerprint — derived from the library and remembered across sessions."
      />

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Files" value={memory.stats.files} />
        <Stat label="Projects" value={memory.stats.projects} />
        <Stat label="Avg BPM" value={memory.stats.avg_bpm ?? "—"} />
        <Stat label="Top keys" value={memory.stats.top_keys.join(", ") || "—"} />
      </div>

      {memory.derived.length > 0 && (
        <ul className="mt-4 space-y-1.5 text-sm text-muted-foreground">
          {memory.derived.map((line: string) => (
            <li key={line} className="flex items-start gap-2">
              <span className="mt-1.5 size-1 shrink-0 rounded-full bg-accent" />
              {line}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4 border-t border-border pt-4">
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Preferences the assistant remembers
        </p>
        <div className="flex flex-wrap gap-1.5">
          {prefs.map((pref) => (
            <span
              key={pref}
              className="inline-flex items-center gap-1 rounded-full border border-accent/30 bg-accent-soft px-2.5 py-1 text-xs text-accent"
            >
              {pref}
              <button
                onClick={() => save(prefs.filter((p) => p !== pref))}
                aria-label={`Remove ${pref}`}
                className="hover:text-foreground"
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
          {prefs.length === 0 && (
            <span className="text-xs text-muted-foreground">
              Add things like “darker kicks”, “Ableton”, “Techno”, “LUFS -8”.
            </span>
          )}
        </div>
        <div className="mt-3 flex gap-2">
          <input
            className="input"
            placeholder="Add a preference…"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && draft.trim()) {
                save([...prefs, draft.trim()]);
                setDraft("");
              }
            }}
          />
          <Button
            variant="soft"
            onClick={() => {
              if (draft.trim()) {
                save([...prefs, draft.trim()]);
                setDraft("");
              }
            }}
          >
            <Plus className="size-4" /> Add
          </Button>
        </div>
      </div>
    </Card>
  );
}

function SessionTimeline({ assets }: { assets: SessionAsset[] }) {
  const events = [...assets]
    .filter((a) => a.date_added)
    .sort((a, b) => (b.date_added! > a.date_added! ? 1 : -1))
    .slice(0, 20);

  const groups = new Map<string, SessionAsset[]>();
  for (const asset of events) {
    const day = new Date(asset.date_added!).toLocaleDateString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric"
    });
    groups.set(day, [...(groups.get(day) ?? []), asset]);
  }

  return (
    <Card className="p-4">
      <SectionTitle
        icon={<CalendarClock className="size-5" />}
        title="Session Timeline"
        subtitle="A git-like history of what entered your studio and when."
      />
      {events.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">Upload files to start your timeline.</p>
      ) : (
        <div className="mt-4 space-y-4">
          {[...groups.entries()].map(([day, dayAssets]) => (
            <div key={day} className="relative border-l border-border pl-4">
              <div className="absolute -left-[5px] top-1 size-2.5 rounded-full bg-accent" />
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{day}</p>
              <div className="mt-1.5 space-y-1.5">
                {dayAssets.map((asset) => (
                  <div key={asset.id} className="flex items-center gap-2 text-sm">
                    {asset.display_type === "Audio" ? (
                      <FileAudio className="size-4 text-accent" />
                    ) : asset.display_type === "MIDI" ? (
                      <Music4 className="size-4 text-accent" />
                    ) : (
                      <FileText className="size-4 text-accent" />
                    )}
                    <span className="truncate">{asset.file_name}</span>
                    <Badge tone="neutral">{asset.project_name}</Badge>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
