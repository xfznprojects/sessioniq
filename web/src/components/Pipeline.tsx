import {
  Blocks,
  Bot,
  Boxes,
  ChevronDown,
  Database,
  FileAudio,
  FileText,
  MessageSquare,
  Music4,
  Search,
  ShieldCheck,
  Upload,
  type LucideIcon
} from "lucide-react";
import { motion } from "framer-motion";
import { useEffect, useState } from "react";

import { Badge, Card, SectionTitle } from "./ui";
import { cn, EASE_OUT } from "../lib/utils";
import type { PipelineResponse, PipelineStage } from "../types";

// Decorative stagger on mount; short delays so the interface never feels slow.
const stagger = (index: number) => ({
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.25, ease: EASE_OUT, delay: Math.min(index * 0.04, 0.4) }
});

const ICONS: Record<string, LucideIcon> = {
  upload: Upload,
  audio: FileAudio,
  midi: Music4,
  notes: FileText,
  embeddings: Boxes,
  vectordb: Database,
  retriever: Search,
  llm: Bot,
  validation: ShieldCheck,
  answer: MessageSquare
};

const STATE_TONE = {
  active: "green",
  available: "neutral",
  fallback: "amber"
} as const;

export function PipelineView({ pipeline }: { pipeline: PipelineResponse | null }) {
  if (!pipeline) {
    return (
      <Card className="p-4">
        <SectionTitle title="Pipeline" subtitle="Loading the live architecture…" />
      </Card>
    );
  }
  return (
    <div className="space-y-6">
      <Card className="p-5">
        <SectionTitle
          icon={<Boxes className="size-5" />}
          title="AI Pipeline"
          subtitle="Every question flows through this ingestion → retrieval → generation → validation path."
          actions={
            <div className="flex gap-2">
              <Badge tone="accent">{pipeline.engine.model}</Badge>
              <Badge tone={pipeline.vector_search ? "green" : "amber"}>
                {pipeline.vector_search ? "vector search on" : "lexical only"}
              </Badge>
            </div>
          }
        />
        <div className="mt-5">
          {pipeline.stages.map((stage, index) => (
            <StageNode key={stage.id} stage={stage} index={index} last={index === pipeline.stages.length - 1} />
          ))}
        </div>
      </Card>
      <PluginsPanel />
    </div>
  );
}

const PLUGIN_STATUS_TONE = {
  active: "green",
  optional: "accent",
  inactive: "amber"
} as const;

function PluginsPanel() {
  const [registry, setRegistry] = useState<any>(null);
  useEffect(() => {
    fetch("/api/plugins").then((r) => r.json()).then(setRegistry).catch(() => setRegistry(null));
  }, []);
  if (!registry) return null;
  return (
    <Card className="p-5">
      <SectionTitle
        icon={<Blocks className="size-5" />}
        title="Analysis Plugins"
        subtitle="Modular analyzers run at ingestion. The registry is declarative, so the platform stays extensible."
      />
      <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-2">
        {registry.plugins.map((plugin: any, index: number) => (
          <motion.div key={plugin.name} {...stagger(index)} className="rounded-md border border-border bg-elevated/50 p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium">{plugin.name}</span>
              <Badge tone={(PLUGIN_STATUS_TONE as any)[plugin.status] ?? "neutral"}>{plugin.status}</Badge>
            </div>
            <p className="mt-0.5 text-xs text-muted-foreground">{plugin.detail}</p>
            <div className="mt-1.5 flex items-center gap-2 text-[0.7rem] text-muted-foreground">
              <span className="rounded bg-muted px-1.5 py-0.5">{plugin.category}</span>
              <span>{plugin.engine}</span>
            </div>
          </motion.div>
        ))}
      </div>
      <div className="mt-4 border-t border-border pt-4">
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Planned integrations</p>
        <div className="flex flex-wrap gap-1.5">
          {registry.planned.map((item: any) => (
            <Badge key={item.name} tone="neutral" className="opacity-60">
              {item.name}
            </Badge>
          ))}
        </div>
      </div>
    </Card>
  );
}

function StageNode({ stage, index, last }: { stage: PipelineStage; index: number; last: boolean }) {
  const Icon = ICONS[stage.id] ?? Boxes;
  return (
    <motion.div {...stagger(index)}>
      <div className="flex items-center gap-4 rounded-lg border border-border bg-elevated/50 p-3.5">
        <div
          className={cn(
            "grid size-10 shrink-0 place-items-center rounded-lg border",
            stage.state === "fallback"
              ? "border-warning/30 bg-[color-mix(in_oklab,var(--warning)_12%,transparent)] text-warning"
              : "border-accent/30 bg-accent-soft text-accent"
          )}
        >
          <Icon className="size-5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-mono text-muted-foreground">{String(index + 1).padStart(2, "0")}</span>
            <h3 className="font-semibold tracking-tight">{stage.title}</h3>
            <Badge tone="neutral">{stage.tech}</Badge>
          </div>
          <p className="mt-0.5 text-sm text-muted-foreground">{stage.detail}</p>
        </div>
        <Badge tone={STATE_TONE[stage.state]}>{stage.state}</Badge>
      </div>
      {!last && (
        <div className="flex justify-center py-1 text-muted-foreground/40">
          <ChevronDown className="size-4" />
        </div>
      )}
    </motion.div>
  );
}
