import { Plus, Sparkles, Tag as TagIcon, X } from "lucide-react";
import { useState } from "react";
import { FileAudio, FileText, Image as ImageIcon, Music4 } from "lucide-react";

import { Button } from "./ui";
import { cn } from "../lib/utils";
import type { AssetTag } from "../types";

// Categorical color per file type — applied to icons so rows/cards are
// trackable by color without turning text into a rainbow.
const TYPE_META: Record<string, { color: string; Icon: typeof FileAudio }> = {
  Audio: { color: "text-type-audio", Icon: FileAudio },
  MIDI: { color: "text-type-midi", Icon: Music4 },
  Notes: { color: "text-type-note", Icon: FileText },
  Image: { color: "text-type-image", Icon: ImageIcon }
};

export function TypeIcon({ type, className }: { type: string; className?: string }) {
  const meta = TYPE_META[type] ?? { color: "text-muted-foreground", Icon: FileText };
  const Icon = meta.Icon;
  return <Icon className={cn("size-4 shrink-0", meta.color, className)} />;
}

export function typeTextColor(type: string): string {
  return TYPE_META[type]?.color ?? "text-muted-foreground";
}

// Named tag colors → pill styles + swatch. Users pick one when adding a tag.
export const TAG_COLORS = ["neutral", "blue", "green", "amber", "red", "violet", "teal"] as const;
const TAG_PILL: Record<string, string> = {
  neutral: "border-border bg-muted text-muted-foreground",
  blue: "border-accent/40 text-accent bg-accent/15",
  green: "border-success/40 text-success bg-success/15",
  amber: "border-warning/40 text-warning bg-warning/15",
  red: "border-danger/40 text-danger bg-danger/15",
  violet: "border-type-midi/40 text-type-midi bg-type-midi/15",
  teal: "border-type-image/40 text-type-image bg-type-image/15"
};
const TAG_SWATCH: Record<string, string> = {
  neutral: "bg-muted-foreground/50",
  blue: "bg-accent",
  green: "bg-success",
  amber: "bg-warning",
  red: "bg-danger",
  violet: "bg-type-midi",
  teal: "bg-type-image"
};
function tagPill(tag: AssetTag): string {
  if (tag.color && TAG_PILL[tag.color]) return TAG_PILL[tag.color];
  return tag.ai_suggested ? TAG_PILL.blue : TAG_PILL.neutral;
}

export function TagList({ tags }: { tags: AssetTag[] }) {
  if (!tags.length) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {tags.map((tag, index) => (
        <span
          key={`${tag.label}-${index}`}
          className={cn(
            "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
            tagPill(tag)
          )}
        >
          {tag.ai_suggested && <Sparkles className="size-3" />}
          {tag.label}
        </span>
      ))}
    </div>
  );
}

export function TagEditor({ tags, onChange }: { tags: AssetTag[]; onChange: (tags: AssetTag[]) => void }) {
  const [label, setLabel] = useState("");
  const [color, setColor] = useState<string>("blue");

  function add() {
    const clean = label.trim();
    if (!clean) return;
    if (tags.some((t) => t.label.toLowerCase() === clean.toLowerCase())) {
      setLabel("");
      return;
    }
    onChange([...tags, { label: clean, ai_suggested: false, color }]);
    setLabel("");
  }

  return (
    <div>
      <h3 className="mb-2 flex items-center gap-1.5 text-sm font-medium text-muted-foreground">
        <TagIcon className="size-4" /> Tags
      </h3>
      {tags.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {tags.map((tag, index) => (
            <span
              key={`${tag.label}-${index}`}
              className={cn(
                "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
                tagPill(tag)
              )}
            >
              {tag.ai_suggested && <Sparkles className="size-3" />}
              {tag.label}
              <button
                onClick={() => onChange(tags.filter((_, i) => i !== index))}
                className="opacity-60 transition-opacity hover:opacity-100"
                aria-label={`Remove ${tag.label}`}
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <input
          className="input h-8 w-36"
          placeholder="Add a tag…"
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              add();
            }
          }}
        />
        <div className="flex items-center gap-1">
          {TAG_COLORS.map((option) => (
            <button
              key={option}
              onClick={() => setColor(option)}
              aria-label={`${option} tag color`}
              title={option}
              className={cn(
                "size-5 rounded-full border border-border/50 transition-transform hover:scale-110",
                TAG_SWATCH[option],
                color === option && "ring-2 ring-ring ring-offset-1 ring-offset-card"
              )}
            />
          ))}
        </div>
        <Button variant="soft" size="sm" onClick={add}>
          <Plus className="size-4" /> Add
        </Button>
      </div>
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="mt-4 rounded-md border border-dashed border-border bg-muted/30 px-4 py-10 text-center text-sm text-muted-foreground">
      {message}
    </div>
  );
}
