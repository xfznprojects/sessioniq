import { motion } from "framer-motion";
import {
  CalendarClock,
  CircleHelp,
  GitCompareArrows,
  Lightbulb,
  ListChecks,
  MessageSquareQuote,
  Search,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Wand2
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge, Button, Card, SectionTitle, Stat } from "./ui";
import { requestJson } from "../lib/api";
import { cn, EASE_OUT } from "../lib/utils";
import type {
  Feedback,
  NextUpEntry,
  QueryLogEntry,
  QueryLogResponse,
  SessionAsset,
  WeeklyDigest
} from "../types";

const stagger = (index: number) => ({
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.22, ease: EASE_OUT, delay: Math.min(index * 0.05, 0.4) }
});

const CREATIVE_INSIGHTS = [
  "Which projects sound unfinished?",
  "Which tracks still need mastering?",
  "Which songs share a similar atmosphere?",
  "Which songs could fit together as an EP?",
  "Which project should I finish next?",
  "What did we decide recently?",
  "Which files might be duplicates?",
  "What tempo and key range does my library cover?"
];

const DIMENSION_LABELS: Record<string, string> = {
  tempo: "Tempo",
  brightness: "Brightness",
  loudness: "Loudness",
  duration: "Length",
  key: "Key"
};

export function InsightsView({
  assets,
  scope,
  onRunInsight
}: {
  assets: SessionAsset[];
  scope: string;
  onRunInsight: (question: string) => void;
}) {
  return (
    <div className="space-y-6">
      <CreativeInsights onRunInsight={onRunInsight} />
      <NextUpCard onAsk={onRunInsight} />
      <WeeklyDigestCard />
      <SemanticSearch scope={scope} />
      <SimilarityEngine assets={assets} />
      <QueryLogCard />
    </div>
  );
}

function NextUpCard({ onAsk }: { onAsk: (question: string) => void }) {
  const [entries, setEntries] = useState<NextUpEntry[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/next-up")
      .then(response => response.json())
      .then(data => setEntries(data.ranking ?? []))
      .catch(() => setError("Could not load the ranking."));
  }, []);

  return (
    <Card className="p-4">
      <SectionTitle
        icon={<ListChecks className="size-5" />}
        title="What to Finish Next"
        subtitle="Ranked by readiness, task progress, and how recently you touched it."
      />
      {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
      {entries === null && !error && <p role="status" className="mt-3 text-sm text-muted-foreground">Ranking your projects…</p>}
      {entries?.length === 0 && (
        <p className="mt-3 text-sm text-muted-foreground">Upload files to get a ranking.</p>
      )}
      <div className="mt-3 space-y-2">
        {entries?.slice(0, 5).map((entry, index) => (
          <div
            key={entry.project_name}
            className="flex items-start justify-between gap-3 rounded-md border border-border bg-background/40 p-2.5"
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">
                <span className="mr-1.5 text-muted-foreground">{index + 1}.</span>
                {entry.project_name}
              </p>
              <p className="mt-0.5 truncate text-xs text-muted-foreground">{entry.reasons.join(" · ")}</p>
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              {entry.stalled && <Badge tone="amber">stalled</Badge>}
              {entry.open_tasks > 0 && <Badge tone="neutral">{entry.open_tasks} open</Badge>}
            </div>
          </div>
        ))}
      </div>
      {entries && entries.length > 0 && (
        <Button size="sm" variant="ghost" className="mt-3" onClick={() => onAsk("What should I finish next?")}>
          <Wand2 className="size-3.5" /> Ask the assistant why
        </Button>
      )}
    </Card>
  );
}

function WeeklyDigestCard() {
  const [digest, setDigest] = useState<WeeklyDigest | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/digest")
      .then(response => response.json())
      .then(setDigest)
      .catch(() => setError("Could not load the digest."));
  }, []);

  return (
    <Card className="p-4">
      <SectionTitle
        icon={<CalendarClock className="size-5" />}
        title="Weekly Digest"
        subtitle="The catalog at a glance — what stalled, what shipped, what's new."
      />
      {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
      {!digest && !error && <p role="status" className="mt-3 text-sm text-muted-foreground">Summarizing your library…</p>}
      {digest && (
        <>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="Stalled" value={digest.stalled_count} hint="Untouched 14+ days with work left" />
            <Stat label="Ready to ship" value={digest.ready_count} />
            <Stat label="Added this week" value={digest.added_this_week.count} />
            <Stat label="Open tasks" value={digest.open_tasks} />
          </div>
          {digest.stalled.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Stalled the longest</p>
              <ul className="mt-1.5 space-y-1 text-sm">
                {digest.stalled.slice(0, 5).map(item => (
                  <li key={item.asset_id} className="flex items-center justify-between gap-2 text-muted-foreground">
                    <span className="truncate">
                      <span className="text-foreground">{item.file_name}</span> · {item.project_name}
                    </span>
                    <span className="shrink-0 text-xs text-warning">{item.days_idle}d idle</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {digest.projects_without_reference.length > 0 && (
            <p className="mt-3 text-xs text-muted-foreground">
              No reference track yet: {digest.projects_without_reference.slice(0, 4).join(", ")}
              {digest.projects_without_reference.length > 4 ? ", …" : ""}
            </p>
          )}
        </>
      )}
    </Card>
  );
}

function QueryLogCard() {
  const [data, setData] = useState<QueryLogResponse | null>(null);
  const [error, setError] = useState("");
  const [unansweredOnly, setUnansweredOnly] = useState(false);

  const load = useCallback((unanswered: boolean) => {
    fetch(`/api/queries?limit=20${unanswered ? "&unanswered=true" : ""}`)
      .then(response => response.json())
      .then(setData)
      .catch(() => setError("Could not load the query log."));
  }, []);

  useEffect(() => { load(unansweredOnly); }, [load, unansweredOnly]);

  async function sendFeedback(entry: QueryLogEntry, feedback: Feedback) {
    const next = entry.feedback === feedback ? null : feedback;
    try {
      await requestJson(`/api/queries/${encodeURIComponent(entry.id)}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feedback: next })
      });
      load(unansweredOnly);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save feedback.");
    }
  }

  const stats = data?.stats;
  return (
    <Card className="p-4">
      <SectionTitle
        icon={<MessageSquareQuote className="size-5" />}
        title="Query Log"
        subtitle="Every question with its quality report and your feedback — the backlog for making the library easier to answer."
        actions={
          <Button
            size="sm"
            variant={unansweredOnly ? "soft" : "ghost"}
            onClick={() => setUnansweredOnly(value => !value)}
            aria-pressed={unansweredOnly}
          >
            <CircleHelp className="size-3.5" /> Unanswered only
          </Button>
        }
      />
      {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
      {stats && (
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="Questions" value={stats.total} />
          <Stat label="Unanswered" value={stats.unanswered} />
          <Stat label="Helpful" value={stats.feedback_up} />
          <Stat label="Not helpful" value={stats.feedback_down} />
        </div>
      )}
      {data && data.entries.length === 0 && (
        <p className="mt-3 text-sm text-muted-foreground">
          {unansweredOnly
            ? "Every question so far was grounded — nothing on the backlog."
            : "Ask the assistant something; every answer lands here with its provenance."}
        </p>
      )}
      <div className="mt-3 space-y-2">
        {data?.entries.map(entry => {
          const unanswered =
            !entry.sources_retrieved || (entry.confidence === "low" && !entry.files_cited);
          return (
            <div
              key={entry.id}
              className={cn(
                "flex items-start justify-between gap-3 rounded-md border p-2.5",
                unanswered ? "border-warning/40 bg-warning/5" : "border-border bg-background/40"
              )}
            >
              <div className="min-w-0">
                <p className="truncate text-sm text-foreground" title={entry.question}>{entry.question}</p>
                <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
                  <span>{entry.ts?.slice(0, 10)}</span>
                  <span>· {entry.model ?? entry.engine}</span>
                  {entry.confidence && <span>· {entry.confidence} confidence</span>}
                  {entry.files_cited != null && <span>· {entry.files_cited} cited</span>}
                  {entry.tool_calls?.length ? <span>· {entry.tool_calls.length} tool call{entry.tool_calls.length === 1 ? "" : "s"}</span> : null}
                  {unanswered && <span className="font-medium text-warning">· not grounded</span>}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Button
                  size="icon" variant="ghost" aria-label="Mark helpful"
                  className={cn("size-7", entry.feedback === "up" ? "text-success" : "text-muted-foreground")}
                  onClick={() => void sendFeedback(entry, "up")}
                >
                  <ThumbsUp className="size-3.5" />
                </Button>
                <Button
                  size="icon" variant="ghost" aria-label="Mark unhelpful"
                  className={cn("size-7", entry.feedback === "down" ? "text-danger" : "text-muted-foreground")}
                  onClick={() => void sendFeedback(entry, "down")}
                >
                  <ThumbsDown className="size-3.5" />
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function CreativeInsights({ onRunInsight }: { onRunInsight: (question: string) => void }) {
  return (
    <Card className="p-4">
      <SectionTitle
        icon={<Wand2 className="size-5" />}
        title="Creative Insights"
        subtitle="Ask across your whole library, not just one file. Answers appear in the assistant."
      />
      <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {CREATIVE_INSIGHTS.map((prompt) => (
          <button
            key={prompt}
            onClick={() => onRunInsight(prompt)}
            className="flex items-center gap-2 rounded-md border border-border bg-elevated/50 px-3 py-2.5 text-left text-sm transition-colors hover:border-accent/40 hover:bg-accent-soft/40"
          >
            <Sparkles className="size-4 shrink-0 text-accent" />
            {prompt}
          </button>
        ))}
      </div>
    </Card>
  );
}

function SemanticSearch({ scope }: { scope: string }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<any[] | null>(null);
  const [loading, setLoading] = useState(false);

  async function run() {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const response = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          project_name: scope === "All Projects" ? null : scope
        })
      });
      setResults((await response.json()).results ?? []);
    } finally {
      setLoading(false);
    }
  }

  const maxScore = Math.max(...(results ?? []).map((r) => r.score ?? 0), 0.0001);

  return (
    <Card className="p-4">
      <SectionTitle
        icon={<Search className="size-5" />}
        title="Semantic Search"
        subtitle="Find files by meaning — “tracks that still need mastering”, not filenames."
      />
      <div className="mt-3 flex gap-2">
        <input
          className="input"
          placeholder="Describe what you're looking for…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => event.key === "Enter" && run()}
        />
        <Button variant="primary" onClick={run} disabled={loading}>
          <Search className="size-4" /> {loading ? "Searching…" : "Search"}
        </Button>
      </div>
      {results && (
        <div className="mt-4 space-y-2">
          {results.length === 0 && (
            <p className="text-sm text-muted-foreground">No matches. Try a broader phrase.</p>
          )}
          {results.map((asset, index) => (
            <motion.div key={asset.id} {...stagger(index)} className="rounded-md border border-border bg-background/40 p-3">
              <div className="flex items-center justify-between gap-2 text-sm">
                <span className="truncate font-medium">{asset.file_name}</span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {asset.bpm ? `${asset.bpm.toFixed(0)} BPM · ` : ""}
                  {asset.key ?? asset.display_type} · {asset.project_name}
                </span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-accent"
                  style={{ width: `${Math.max((asset.score / maxScore) * 100, 4)}%` }}
                />
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </Card>
  );
}

function SimilarityEngine({ assets }: { assets: SessionAsset[] }) {
  const analyzable = useMemo(
    () => assets.filter((a) => a.display_type === "Audio" || a.display_type === "MIDI"),
    [assets]
  );
  const [targetId, setTargetId] = useState<string>("");
  const [matches, setMatches] = useState<any[] | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!targetId && analyzable[0]) setTargetId(analyzable[0].id);
  }, [analyzable, targetId]);

  useEffect(() => {
    if (!targetId) return;
    setLoading(true);
    fetch(`/api/assets/${encodeURIComponent(targetId)}/similar`)
      .then((r) => r.json())
      .then((d) => setMatches(d.matches ?? []))
      .finally(() => setLoading(false));
  }, [targetId]);

  const target = analyzable.find((a) => a.id === targetId);

  return (
    <Card className="p-4">
      <SectionTitle
        icon={<GitCompareArrows className="size-5" />}
        title="Similarity Engine"
        subtitle="Content-based similarity from tempo, brightness, loudness, length, and key."
      />
      {analyzable.length < 2 ? (
        <p className="mt-3 text-sm text-muted-foreground">
          Upload at least two audio or MIDI files to compare them.
        </p>
      ) : (
        <>
          <div className="mt-3 flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Compare</span>
            <select
              className="select-compact flex-1"
              value={targetId}
              onChange={(event) => setTargetId(event.target.value)}
            >
              {analyzable.map((asset) => (
                <option key={asset.id} value={asset.id}>
                  {asset.file_name}
                </option>
              ))}
            </select>
          </div>
          {loading && <p className="mt-3 text-sm text-muted-foreground">Analyzing…</p>}
          {!loading && matches && (
            <div className="mt-4 space-y-3">
              {matches.length === 0 && (
                <p className="text-sm text-muted-foreground">No comparable files yet.</p>
              )}
              {matches.map((match) => (
                <div key={match.id} className="rounded-md border border-border bg-background/40 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{match.file_name}</p>
                      <p className="text-xs text-muted-foreground">{match.project_name}</p>
                    </div>
                    <div className="text-right">
                      <div className="text-xl font-semibold tracking-tight text-accent">
                        {Math.round(match.score * 100)}%
                      </div>
                      <div className="text-[0.65rem] uppercase tracking-wide text-muted-foreground">
                        similar
                      </div>
                    </div>
                  </div>
                  {match.highlights?.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {match.highlights.map((h: string) => (
                        <Badge key={h} tone="accent">
                          {h}
                        </Badge>
                      ))}
                    </div>
                  )}
                  <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5">
                    {Object.entries(match.dimensions).map(([dim, value]) => (
                      <div key={dim} className="text-xs">
                        <div className="flex justify-between text-muted-foreground">
                          <span>{DIMENSION_LABELS[dim] ?? dim}</span>
                          <span>{Math.round((value as number) * 100)}%</span>
                        </div>
                        <div className="mt-0.5 h-1 overflow-hidden rounded-full bg-muted">
                          <div
                            className={cn("h-full rounded-full", (value as number) >= 0.6 ? "bg-accent" : "bg-muted-foreground/40")}
                            style={{ width: `${Math.max((value as number) * 100, 3)}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
              {target && (
                <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Lightbulb className="size-3.5" /> Compared against {target.file_name} using extracted audio features.
                </p>
              )}
            </div>
          )}
        </>
      )}
    </Card>
  );
}
