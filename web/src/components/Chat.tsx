import { motion } from "framer-motion";
import {
  Bot,
  BookmarkPlus,
  CheckCircle2,
  FileText,
  Lightbulb,
  RotateCcw,
  SendHorizontal,
  ThumbsDown,
  ThumbsUp
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Badge, Button, Card, SectionTitle } from "./ui";
import { cn, EASE_OUT } from "../lib/utils";
import type { AiStatus, ChatMessage, Feedback } from "../types";

const CONFIDENCE_TONE: Record<string, "green" | "amber" | "red"> = {
  high: "green",
  medium: "amber",
  low: "red"
};

export function ChatPanel({
  question,
  setQuestion,
  askQuestion,
  messages,
  clearConversation,
  loading,
  aiStatus,
  scope,
  onSaveDecision,
  savedDecisionIds,
  feedback,
  onFeedback
}: {
  question: string;
  setQuestion: (question: string) => void;
  askQuestion: () => void;
  messages: ChatMessage[];
  clearConversation: () => void;
  loading: boolean;
  aiStatus: AiStatus | null;
  scope: string;
  onSaveDecision: (message: ChatMessage) => void;
  savedDecisionIds: Set<number>;
  feedback: Record<number, Feedback>;
  onFeedback: (message: ChatMessage, feedback: Feedback) => void;
}) {
  const suggestions = [
    "What still needs work?",
    "Which track is the fastest?",
    "What key do these share?",
    "What did we decide?"
  ];
  const thread = useRef<HTMLDivElement>(null);
  const lastMessage = messages[messages.length - 1];
  const hints = aiStatus?.hints ?? [];

  useEffect(() => {
    // Keep the newest turn in view as the thread grows or streams.
    thread.current?.scrollTo({ top: thread.current.scrollHeight });
  }, [messages]);

  return (
    <Card className="p-4 glow">
      <SectionTitle
        icon={<Bot className="size-5" />}
        title="Ask SessionIQ"
        actions={
          <div className="flex items-center gap-2">
            {messages.length > 0 && (
              <Button size="sm" variant="ghost" onClick={clearConversation} title="Start a fresh conversation">
                <RotateCcw className="size-3.5" /> Clear
              </Button>
            )}
            {aiStatus && (
              <Badge tone={aiStatus.answering?.mode === "rules" ? "amber" : "green"}>
                {aiStatus.answering?.mode === "rules" ? "Rules engine" : aiStatus.answering?.model}
                {aiStatus.vector_search ? " · vector" : ""}
              </Badge>
            )}
          </div>
        }
      />
      <p className="mt-1 text-xs text-muted-foreground">
        Source-cited answers scoped to <span className="text-foreground">{scope}</span>.
        Follow-ups work — ask “what about its key?”.
      </p>

      {hints.length > 0 && (
        <details className="mt-3 rounded-md border border-border p-2 text-xs text-muted-foreground"><summary className="cursor-pointer">Optional AI setup</summary><div className="mt-2 space-y-2">
          {hints.map((hint: string) => (
            <p key={hint}>{hint}</p>
          ))}
        </div></details>
      )}

      <div ref={thread} className="mt-3 max-h-[46vh] space-y-3 overflow-y-auto pr-1" aria-live="polite">
        {messages.length === 0 && (
          <p className="rounded-md border border-dashed border-border bg-muted/30 px-3 py-6 text-center text-xs text-muted-foreground">
            Ask anything about your files — tasks, tempo, keys, loudness, status, or decisions.
            The answer cites the exact sources it used.
          </p>
        )}
        {messages.map(message =>
          message.role === "user" ? (
            <div key={message.id} className="flex justify-end">
              <p className="max-w-[85%] rounded-lg border border-accent/30 bg-accent-soft/60 px-3 py-2 text-sm text-foreground">
                {message.content}
              </p>
            </div>
          ) : (
            <AssistantMessage
              key={message.id}
              message={message}
              onSaveDecision={() => onSaveDecision(message)}
              decisionSaved={savedDecisionIds.has(message.id)}
              feedback={feedback[message.id]}
              onFeedback={(value) => onFeedback(message, value)}
            />
          )
        )}
      </div>

      <div className="mt-3">
        <textarea
          className="input min-h-20 resize-none"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) askQuestion();
          }}
          placeholder={lastMessage?.role === "assistant" ? "Follow up: “what about its key?”…" : "What still needs work? Which files are ready?"}
        />
        <div className="mt-2 flex flex-wrap gap-1.5">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              onClick={() => setQuestion(suggestion)}
              className="rounded-full border border-border bg-muted/60 px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:border-accent/40 hover:text-foreground"
            >
              {suggestion}
            </button>
          ))}
        </div>
        <Button variant="primary" className="mt-3 w-full" onClick={askQuestion} disabled={loading}>
          <SendHorizontal className="size-4" /> {loading ? "Thinking…" : "Ask"}
        </Button>
      </div>
    </Card>
  );
}

function AssistantMessage({
  message,
  onSaveDecision,
  decisionSaved,
  feedback,
  onFeedback
}: {
  message: ChatMessage;
  onSaveDecision: () => void;
  decisionSaved: boolean;
  feedback?: Feedback;
  onFeedback: (feedback: Feedback) => void;
}) {
  const result = message.result;
  const citations = result?.answer.citations ?? [];
  const sources = result?.sources ?? [];
  if (message.pending && !message.content) {
    return (
      <div className="rounded-md border border-border bg-background/40 p-3 text-sm text-muted-foreground" role="status">
        <span className="mr-2 inline-block size-2 animate-pulse rounded-full bg-accent" />
        {message.status ?? "Checking your sources…"}
      </div>
    );
  }
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: EASE_OUT }}
      className="rounded-md border border-border bg-background/40 p-3 text-sm"
    >
      <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
      {message.pending && (
        <p role="status" className="mt-1.5 flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="inline-block size-1.5 animate-pulse rounded-full bg-accent" />
          {message.status ?? "Writing…"}
        </p>
      )}

      {result?.standalone_question && (
        <p className="mt-2 text-xs text-muted-foreground">
          <Lightbulb className="mr-1 inline size-3.5" />
          Interpreted as: <span className="text-foreground-secondary">{result.standalone_question}</span>
        </p>
      )}

      {result?.quality && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          <Badge tone={CONFIDENCE_TONE[result.quality.confidence] ?? "neutral"}>
            {result.quality.confidence} confidence
          </Badge>
          <Badge tone="neutral">{result.quality.model}</Badge>
          <Badge tone="neutral">prompt {result.quality.prompt_version}</Badge>
          <Badge tone="neutral">{Math.round(result.quality.processing_ms)} ms</Badge>
          {result.quality.tool_calls?.length ? (
            <Badge tone="blue">tools: {result.quality.tool_calls.map(call => call.name).join(", ")}</Badge>
          ) : null}
        </div>
      )}

      {citations.length > 0 && (
        <div className="mt-3 space-y-1.5 border-t border-border pt-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Sources</p>
          {citations.map((citation, index) => (
            <div
              key={`${citation.file_name}-${index}`}
              className="flex items-start gap-2 text-xs"
            >
              <FileText className="mt-0.5 size-3.5 shrink-0 text-accent" />
              <span>
                <span className="font-medium text-foreground">{citation.file_name}</span>
                <span className="text-muted-foreground"> — {citation.evidence}</span>
              </span>
            </div>
          ))}
        </div>
      )}

      {sources.length > 0 && <WhyExplainer sources={sources} />}

      {!message.pending && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {result?.query_id && (
            <div className="flex items-center gap-1" role="group" aria-label="Was this answer helpful?">
              <Button
                size="icon"
                variant="ghost"
                aria-label="Helpful answer"
                title="Helpful answer"
                className={cn("size-7", feedback === "up" ? "text-success" : "text-muted-foreground")}
                disabled={feedback === "up"}
                onClick={() => onFeedback("up")}
              >
                <ThumbsUp className="size-3.5" />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                aria-label="Unhelpful answer"
                title="Unhelpful answer"
                className={cn("size-7", feedback === "down" ? "text-danger" : "text-muted-foreground")}
                disabled={feedback === "down"}
                onClick={() => onFeedback("down")}
              >
                <ThumbsDown className="size-3.5" />
              </Button>
            </div>
          )}
          <Button
            size="sm"
            variant={decisionSaved ? "ghost" : "outline"}
            disabled={decisionSaved}
            onClick={onSaveDecision}
            title="Remember this in the Studio's decision log"
          >
            {decisionSaved ? <CheckCircle2 className="size-3.5" /> : <BookmarkPlus className="size-3.5" />}
            {decisionSaved ? "Saved to decisions" : "Save as decision"}
          </Button>
        </div>
      )}
    </motion.div>
  );
}

function WhyExplainer({ sources }: { sources: any[] }) {
  const [open, setOpen] = useState(false);
  const maxScore = Math.max(...sources.map((s) => s.score ?? 0), 0.0001);
  const toolCount = sources.filter((s) => s.via === "tool").length;
  return (
    <div className="mt-3 border-t border-border pt-3">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 text-xs font-medium text-accent hover:underline"
      >
        <Lightbulb className="size-3.5" /> {open ? "Hide reasoning" : "Why this answer?"}
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          <p className="text-xs text-muted-foreground">
            Retrieved {sources.length - toolCount} source{sources.length - toolCount === 1 ? "" : "s"} by relevance
            {toolCount > 0 ? ` and pulled ${toolCount} via metadata tool${toolCount === 1 ? "" : "s"}` : ""};
            the answer is grounded only in these.
          </p>
          {sources.map((source) => (
            <div key={source.id} className="text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-medium text-foreground">
                  {source.file_name}
                  {source.via === "tool" && (
                    <Badge tone="blue" className="ml-1.5 align-middle">tool</Badge>
                  )}
                </span>
                <span className="shrink-0 text-muted-foreground">
                  {source.bpm ? `${source.bpm.toFixed(0)} BPM · ` : ""}
                  {source.key ?? source.display_type}
                </span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-accent"
                  style={{ width: `${Math.max((source.score / maxScore) * 100, 4)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
