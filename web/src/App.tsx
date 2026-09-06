import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  SortingState,
  useReactTable
} from "@tanstack/react-table";
import { MotionConfig, motion } from "framer-motion";
import {
  ArrowUpDown,
  Brain,
  CheckCircle2,
  Clock,
  Cpu,
  Disc3,
  FileAudio,
  FileDown,
  FileText,
  Gauge,
  Grid2X2,
  HeartPulse,
  LayoutDashboard,
  Lightbulb,
  List,
  ListChecks,
  Moon,
  Music4,
  Search,
  Sun,
  Telescope,
  Trash2,
  Upload,
  Workflow,
  XCircle
} from "lucide-react";
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Badge, Button, Card, SectionTitle, Stat } from "./components/ui";
import { ConfirmDialog, ContextMenu, type MenuState } from "./components/ContextMenu";
import { Sidebar, type GroupFilter } from "./components/Sidebar";
import { Player, type PlayerSeek } from "./components/Player";
import { ChatPanel } from "./components/Chat";
import { Inspector } from "./components/Inspector";
import { EmptyState, TagList, TypeIcon, typeTextColor } from "./components/shared";
import { requestJson } from "./lib/api";
import { assetsInScope } from "./lib/workspace";
const PipelineView = lazy(() => import("./components/Pipeline").then(m => ({ default: m.PipelineView })));
const InsightsView = lazy(() => import("./components/Insights").then(m => ({ default: m.InsightsView })));
const StudioView = lazy(() => import("./components/Studio").then(m => ({ default: m.StudioView })));
import { readClientAudioTags } from "./lib/audioTags";
import { cn, EASE_OUT, formatSeconds } from "./lib/utils";
import type {
  AiStatus,
  ChatMessage,
  ChatResponse,
  Feedback,
  FileStatus,
  LibraryResponse,
  PipelineResponse,
  ProjectHealth,
  ProjectSummary,
  QualityReport,
  SessionAsset,
  TaskStatus
} from "./types";

type ViewId = "workspace" | "insights" | "studio" | "pipeline";
const VIEWS: { id: ViewId; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "workspace", label: "Workspace", icon: LayoutDashboard },
  { id: "insights", label: "Insights", icon: Telescope },
  { id: "studio", label: "Studio", icon: Brain },
  { id: "pipeline", label: "Pipeline", icon: Workflow }
];

const API = "";
const STATUSES: FileStatus[] = ["Idea", "In Progress", "Needs Work", "Ready", "Reference", "Archived"];
const STATUS_TONE: Record<FileStatus, "neutral" | "green" | "amber" | "red" | "blue"> = {
  Idea: "neutral",
  "In Progress": "blue",
  "Needs Work": "amber",
  Ready: "green",
  Reference: "blue",
  Archived: "neutral"
};

// The conversation survives page reloads like note drafts and player position do.
const CHAT_STORAGE_KEY = "sessioniq-chat";
const PERSISTED_CHAT_TURNS = 40;

function loadPersistedChat(): ChatMessage[] {
  try {
    const raw = JSON.parse(localStorage.getItem(CHAT_STORAGE_KEY) ?? "[]");
    if (!Array.isArray(raw)) return [];
    return raw.filter(
      (message): message is ChatMessage =>
        message && (message.role === "user" || message.role === "assistant") && typeof message.content === "string"
    );
  } catch {
    return [];
  }
}

type ViewMode = "table" | "grid";
type Theme = "dark" | "light";
type Filters = {
  query: string;
  types: string[];
  statuses: FileStatus[];
  bpmMin: string;
  bpmMax: string;
  key: string;
  tag: string;
};

const EMPTY_FILTERS: Filters = { query: "", types: [], statuses: [], bpmMin: "", bpmMax: "", key: "", tag: "" };

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem("sessioniq-theme") as Theme) || "dark"
  );
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("sessioniq-theme", theme);
  }, [theme]);
  return [theme, () => setTheme(t => (t === "dark" ? "light" : "dark"))];
}

export default function App() {
  const [theme, toggleTheme] = useTheme();
  const [library, setLibrary] = useState<LibraryResponse>({ assets: [], projects: [], smartCollections: {} });
  const [selectedProject, setSelectedProject] = useState<string>("All Projects");
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const [collection, setCollection] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(0);
  const [railTab, setRailTab] = useState<"assistant" | "tasks">("assistant");
  const [libraryOpen, setLibraryOpen] = useState(false);
  const mutations = useRef(Promise.resolve());
  const questionSerial = useRef(0);
  const [viewMode, setViewMode] = useState<ViewMode>("table");
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [chatQuestion, setChatQuestion] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(loadPersistedChat);
  const [chatLoading, setChatLoading] = useState(false);
  const [savedDecisions, setSavedDecisions] = useState<Set<number>>(new Set());
  const [feedback, setFeedback] = useState<Record<number, Feedback>>({});
  const [playerSeek, setPlayerSeek] = useState<PlayerSeek | null>(null);
  const [transcribingId, setTranscribingId] = useState<string | null>(null);
  const [reanalyzingId, setReanalyzingId] = useState<string | null>(null);
  const seekNonce = useRef(0);
  const [validation, setValidation] = useState<any>({ checks: [] });
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [activeView, setActiveView] = useState<ViewId>("workspace");
  const [pipeline, setPipeline] = useState<PipelineResponse | null>(null);
  const [fileMenu, setFileMenu] = useState<MenuState | null>(null);
  const [assetToDelete, setAssetToDelete] = useState<SessionAsset | null>(null);

  useEffect(() => {
    void perform(refreshLibrary);
    void perform(refreshValidation);
    fetch(`${API}/api/ai-status`).then((r) => r.json()).then(setAiStatus).catch(() => setAiStatus(null));
    fetch(`${API}/api/pipeline`).then((r) => r.json()).then(setPipeline).catch(() => setPipeline(null));
  }, []);

  useEffect(() => {
    try { localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(chatMessages.slice(-PERSISTED_CHAT_TURNS))); }
    catch { /* The thread still works in memory when storage is unavailable. */ }
  }, [chatMessages]);

  const accent = theme === "dark" ? "oklch(0.66 0.17 256)" : "oklch(0.58 0.19 258)";

  const inScope = (projectName: string) =>
    selectedProject === "All Projects" ||
    projectName === selectedProject ||
    projectName.startsWith(selectedProject + "/");

  const scopedAssets = useMemo(
    () =>
      assetsInScope(library.assets, selectedProject, collection ? library.smartCollections[collection] ?? [] : undefined).filter((asset) => {
        if (filters.query && !asset.file_name.toLowerCase().includes(filters.query.toLowerCase())) return false;
        if (filters.types.length && !filters.types.includes(asset.display_type)) return false;
        if (filters.statuses.length && !filters.statuses.includes(asset.status)) return false;
        if (filters.bpmMin && (!asset.bpm || asset.bpm < Number(filters.bpmMin))) return false;
        if (filters.bpmMax && (!asset.bpm || asset.bpm > Number(filters.bpmMax))) return false;
        if (filters.key && asset.key !== filters.key) return false;
        if (filters.tag && !asset.tags.some((t) => t.label.toLowerCase().includes(filters.tag.toLowerCase())))
          return false;
        return true;
      }),
    [library.assets, library.smartCollections, selectedProject, collection, filters]
  );

  const projectNames = library.projects.map((p) => p.project_name);
  const selectedAsset = scopedAssets.find(a => a.id === selectedAssetId) ?? scopedAssets[0];
  const focusProject = selectedProject === "All Projects" ? undefined
    : library.projects.find(p => p.project_name === selectedProject);
  const scopedProjects = library.projects.filter(p => inScope(p.project_name));
  const scopedTasks = scopedProjects.flatMap(p => p.tasks);
  const openTasks = scopedTasks.filter(t => t.status !== "Done").length;
  const scopeLabel = collection ?? selectedProject;

  function selectProject(project: string) {
    questionSerial.current += 1;
    setChatLoading(false); setChatMessages([]);
    setSelectedProject(project); setCollection(null); setFilters(EMPTY_FILTERS);
    setSelectedAssetId(null); setLibraryOpen(false);
  }

  const chatQuality: QualityReport | undefined =
    [...chatMessages].reverse().find(message => message.result?.quality)?.result?.quality;

  async function perform(action: () => Promise<void>): Promise<boolean> {
    setError("");
    try { await action(); return true; }
    catch (error) { setError(error instanceof Error ? error.message : "Something went wrong. Please retry."); return false; }
  }
  async function refreshLibrary() {
    setLibrary(await requestJson<LibraryResponse>(`${API}/api/library`));
  }
  async function refreshValidation() {
    setValidation(await requestJson(`${API}/api/validation`));
  }
  async function mutate(url: string, method: string, body?: unknown): Promise<boolean> {
    setBusy(count => count + 1);
    let success = false;
    const work = mutations.current.then(async () => {
      success = await perform(async () => {
        const data = await requestJson(url, { method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
        setLibrary(data.library);
      });
    }).finally(() => setBusy(count => count - 1));
    mutations.current = work;
    await work;
    return success;
  }
  async function uploadFiles(form: HTMLFormElement) {
    if (uploading) return;
    setUploading(true);
    await perform(async () => {
      const formData = new FormData(form);
      const fileInput = form.elements.namedItem("files") as HTMLInputElement | null;
      formData.append("client_metadata", JSON.stringify(await readClientAudioTags(fileInput?.files ?? null)));
      await requestJson(`${API}/api/upload`, { method: "POST", body: formData });
      await refreshLibrary(); form.reset(); setUploadOpen(false);
    });
    setUploading(false);
  }
  async function askQuestion(override?: string) {
    const question = (override ?? chatQuestion).trim();
    if (!question || chatLoading) return;
    const serial = ++questionSerial.current;
    setRailTab("assistant");
    if (override) setChatQuestion(override);
    const pendingId = serial * 2 + 1;
    setChatMessages(previous => [
      ...previous,
      { id: serial * 2, role: "user", content: question },
      { id: pendingId, role: "assistant", content: "", pending: true }
    ]);
    setChatLoading(true);
    // The conversation window sent for follow-up resolution on the server.
    const history = chatMessages.slice(-12).map(message => ({ role: message.role, content: message.content }));
    const ok = await perform(async () => {
      const response = await fetch(`${API}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          project_name: selectedProject === "All Projects" ? null : selectedProject,
          history
        })
      });
      if (!response.ok || !response.body) {
        throw new Error(`The assistant request failed (${response.status}).`);
      }
      await consumeAnswerStream(response.body, pendingId, serial);
    });
    if (serial !== questionSerial.current) return;
    setChatLoading(false);
    if (!ok) {
      setChatMessages(previous => previous.map(message =>
        message.id === pendingId
          ? { ...message, pending: false, status: undefined, content: message.content || "(no answer was received)" }
          : message
      ));
    }
  }
  async function consumeAnswerStream(body: ReadableStream<Uint8Array>, pendingId: number, serial: number) {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    const handleFrame = (frame: string) => {
      let kind = "message";
      let dataText = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event: ")) kind = line.slice(7).trim();
        else if (line.startsWith("data: ")) dataText += line.slice(6);
      }
      if (!dataText) return;
      let data: any;
      try { data = JSON.parse(dataText); } catch { return; }
      if (serial !== questionSerial.current) return;
      if (kind === "meta") {
        setChatMessages(previous => previous.map(message =>
          message.id === pendingId && !message.content
            ? { ...message, status: data.standalone_question ? "Interpreting your follow-up…" : undefined }
            : message
        ));
      } else if (kind === "tool") {
        setChatMessages(previous => previous.map(message =>
          message.id === pendingId ? { ...message, status: `Querying library (${data.name})…` } : message
        ));
      } else if (kind === "delta") {
        setChatMessages(previous => previous.map(message =>
          message.id === pendingId
            ? { ...message, content: message.content + data.text, status: undefined }
            : message
        ));
      } else if (kind === "done") {
        const payload = data as ChatResponse;
        setChatMessages(previous => previous.map(message =>
          message.id === pendingId
            ? { ...message, content: payload.answer.answer, result: payload, pending: false, status: undefined }
            : message
        ));
      } else if (kind === "error") {
        throw new Error(data.detail ?? "The answer stream failed.");
      }
    };
    // Server-sent events: frames separated by blank lines; parse as they arrive.
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let separator = buffer.indexOf("\n\n");
      while (separator !== -1) {
        handleFrame(buffer.slice(0, separator));
        buffer = buffer.slice(separator + 2);
        separator = buffer.indexOf("\n\n");
      }
    }
  }
  function clearConversation() {
    questionSerial.current += 1;
    setChatLoading(false);
    setChatMessages([]);
  }
  async function saveDecision(message: ChatMessage) {
    if (savedDecisions.has(message.id)) return;
    const citation = message.result?.answer.citations.find(item => item.asset_id);
    const success = await perform(async () => {
      await requestJson(`${API}/api/decisions`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: message.content.slice(0, 500),
          project_name: selectedProject === "All Projects" ? "Unassigned" : selectedProject,
          source_asset_id: citation?.asset_id ?? null
        })
      });
    });
    if (success) setSavedDecisions(previous => new Set(previous).add(message.id));
  }
  async function sendFeedback(message: ChatMessage, value: Feedback) {
    const queryId = message.result?.query_id;
    if (!queryId) return;
    const next = feedback[message.id] === value ? null : value;
    const success = await perform(async () => {
      await requestJson(`${API}/api/queries/${encodeURIComponent(queryId)}/feedback`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feedback: next })
      });
    });
    if (!success) return;
    setFeedback(previous => {
      if (next === null) {
        const copy = { ...previous };
        delete copy[message.id];
        return copy;
      }
      return { ...previous, [message.id]: next };
    });
  }
  async function exportReport() {
    await perform(async () => {
      const response = await fetch(
        `${API}/api/projects/report?project=${encodeURIComponent(selectedProject)}`
      );
      if (!response.ok) throw new Error(`Report export failed (${response.status}).`);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download =
        selectedProject === "All Projects"
          ? "sessioniq-library-report.md"
          : `sessioniq-report-${selectedProject.replace(/[^a-zA-Z0-9-]+/g, "-")}.md`;
      link.click();
      URL.revokeObjectURL(url);
    });
  }
  async function transcribeAsset(asset: SessionAsset) {
    if (transcribingId) return;
    setTranscribingId(asset.id);
    await perform(async () => {
      await requestJson(`${API}/api/assets/${encodeURIComponent(asset.id)}/transcribe`, {
        method: "POST"
      });
      await refreshLibrary();
    });
    setTranscribingId(null);
  }
  async function reanalyzeAsset(asset: SessionAsset) {
    if (reanalyzingId) return;
    setReanalyzingId(asset.id);
    await perform(async () => {
      await requestJson(`${API}/api/assets/${encodeURIComponent(asset.id)}/reanalyze`, {
        method: "POST"
      });
      await refreshLibrary();
    });
    setReanalyzingId(null);
  }
  function seekTo(assetId: string, time: number) {
    setPlayerSeek({ id: assetId, time, nonce: ++seekNonce.current });
  }
  async function updateAsset(asset: SessionAsset, update: Partial<Pick<SessionAsset, "status" | "tags" | "project_name" | "note">>) {
    return mutate(`${API}/api/assets/${encodeURIComponent(asset.id)}`, "PATCH", update);
  }
  async function doDeleteAsset(asset: SessionAsset) {
    if (await mutate(`${API}/api/assets/${encodeURIComponent(asset.id)}`, "DELETE")) {
      if (selectedAssetId === asset.id) setSelectedAssetId(null);
    }
  }
  async function deleteProject(path: string) {
    if (await mutate(`${API}/api/projects/delete`, "POST", { name: path })) {
      if (selectedProject === path || selectedProject.startsWith(path + "/")) selectProject("All Projects");
    }
  }

  function openFileContext(event: React.MouseEvent, asset: SessionAsset) {
    event.preventDefault();
    setFileMenu({
      x: event.clientX,
      y: event.clientY,
      items: [
        { label: "Open", onSelect: () => setSelectedAssetId(asset.id) },
        {
          label: "Delete",
          danger: true,
          icon: <Trash2 className="size-4" />,
          onSelect: () => setAssetToDelete(asset)
        }
      ]
    });
  }

  async function updateTask(taskId: string, status: TaskStatus) {
    await mutate(`${API}/api/tasks/${taskId}`, "PATCH", { status });
  }
  async function renameProject(oldName: string, newName: string) {
    if (await mutate(`${API}/api/projects/rename`, "POST", { old_name: oldName, new_name: newName })) {
      if (selectedProject === oldName || selectedProject.startsWith(oldName + "/")) {
        selectProject(newName + selectedProject.slice(oldName.length));
      }
    }
  }

  return (
   <MotionConfig reducedMotion="user">
    <div className="dot-grid flex h-screen flex-col overflow-hidden bg-background text-foreground">
    <div className="flex min-h-0 flex-1 flex-col md:flex-row">
      <div className={cn("max-h-64 shrink-0 overflow-y-auto md:max-h-none", libraryOpen ? "block" : "hidden md:block")}>
      <Sidebar
          projects={library.projects}
          assets={library.assets}
          smartCollections={library.smartCollections}
          selectedProject={selectedProject}
          onSelectProject={selectProject}
          selectedCollection={collection}
          onSelectCollection={(name) => {
            selectProject("All Projects"); setCollection(name);
          }}
          onRenameProject={renameProject}
          onDeleteProject={deleteProject}
          onSelectGroup={(project, filter: GroupFilter) => {
            selectProject(project);
            setFilters({ ...EMPTY_FILTERS, ...filter });
          }}
        />
      </div>
      <main className="min-w-0 flex-1 space-y-4 overflow-y-auto p-4 lg:p-6">
          <Button className="md:hidden" size="sm" aria-expanded={libraryOpen} onClick={() => setLibraryOpen(!libraryOpen)}>Library</Button>
          <Header
            theme={theme}
            toggleTheme={toggleTheme}
            uploadFiles={uploadFiles}
            uploading={uploading}
            uploadOpen={uploadOpen}
            setUploadOpen={setUploadOpen}
            projectNames={projectNames}
          />

          {error && <div role="alert" className="flex items-center justify-between gap-3 rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm">
            <span>{error}</span><Button size="sm" variant="ghost" onClick={() => setError("")}>Dismiss</Button>
          </div>}
          {busy > 0 && <p role="status" className="text-xs text-muted-foreground">Saving changes…</p>}
          <ViewTabs active={activeView} onChange={setActiveView} />

          <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
            <motion.div
              key={activeView}
              className="min-w-0 space-y-4"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.22, ease: EASE_OUT }}
            >
              <Suspense fallback={<Card className="p-4" role="status">Loading view…</Card>}>
                {activeView === "workspace" ? (
                  <>
                    <Card className="p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div><p className="text-xs font-medium uppercase tracking-widest text-accent">Your workspace</p>
                          <h2 className="mt-1 text-xl font-semibold">{scopeLabel}</h2>
                          <p className="mt-1 text-sm text-muted-foreground">{scopedAssets.length} files · {openTasks} open tasks{collection ? " across the library" : ""}</p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <Button size="sm" variant="soft" onClick={() => setRailTab("tasks")}>View tasks</Button>
                          <Button size="sm" variant="outline" onClick={() => void exportReport()}>
                            <FileDown className="size-4" /> Export report
                          </Button>
                        </div>
                      </div>
                      {!collection && scopedTasks.find(t => t.status !== "Done") && <p className="mt-3 border-t border-border pt-3 text-sm text-foreground-secondary">
                        <span className="font-medium text-foreground">Next up: </span>{scopedTasks.find(t => t.status !== "Done")?.description}
                      </p>}
                    </Card>
                    {selectedProject === "All Projects" && !collection && <details className="rounded-lg border border-border bg-card p-3">
                      <summary className="cursor-pointer text-sm font-medium">Browse projects <span className="ml-1 text-muted-foreground">({library.projects.length})</span></summary>
                      <ProjectOverview library={library} onSelect={selectProject} />
                    </details>}
                    <Card className="p-4">
                      <SectionTitle
                        title="Files"
                        subtitle="Sort, filter, tag, and organize project files."
                        actions={
                          <div className="flex items-center gap-1 rounded-md border border-border bg-muted/50 p-0.5">
                            <Button
                              variant={viewMode === "table" ? "soft" : "ghost"}
                              size="sm"
                              onClick={() => setViewMode("table")}
                            >
                              <List className="size-4" /> Table
                            </Button>
                            <Button
                              variant={viewMode === "grid" ? "soft" : "ghost"}
                              size="sm"
                              onClick={() => setViewMode("grid")}
                            >
                              <Grid2X2 className="size-4" /> Grid
                            </Button>
                          </div>
                        }
                      />
                      <FiltersPanel filters={filters} setFilters={setFilters} assets={library.assets} />
                      {viewMode === "table" ? (
                        <AssetTable
                          assets={scopedAssets}
                          selectedId={selectedAsset?.id}
                          onSelect={setSelectedAssetId}
                          onUpdate={updateAsset}
                          onContext={openFileContext}
                        />
                      ) : (
                        <AssetGrid
                          assets={scopedAssets}
                          selectedId={selectedAsset?.id}
                          onSelect={setSelectedAssetId}
                          onContext={openFileContext}
                        />
                      )}
                    </Card>
                    {focusProject && <details className="rounded-lg border border-border bg-card p-3"><summary className="cursor-pointer text-sm font-medium">Readiness checklist · {focusProject.health.checks.filter(c => c.ok).length} of {focusProject.health.checks.length} checks</summary><ProjectHealthPanel project={focusProject} /></details>}
                    <Inspector
                      asset={selectedAsset}
                      accent={accent}
                      projectNames={projectNames}
                      onUpdate={updateAsset}
                      onDelete={(asset) => setAssetToDelete(asset)}
                      onSeek={seekTo}
                      onTranscribe={transcribeAsset}
                      transcribingId={transcribingId}
                      canTranscribe={Boolean(aiStatus?.transcription?.available)}
                      onReanalyze={reanalyzeAsset}
                      reanalyzingId={reanalyzingId}
                    />
                  </>
                ) : activeView === "insights" ? (
                  <InsightsView
                    assets={library.assets}
                    scope={selectedProject}
                    onRunInsight={(question) => askQuestion(question)}
                  />
                ) : activeView === "studio" ? (
                  <StudioView assets={library.assets} />
                ) : (
                  <PipelineView pipeline={pipeline} />
                )}
              </Suspense>
            </motion.div>

            <aside className="min-w-0 space-y-3 xl:sticky xl:top-4">
              <div className="flex gap-1 rounded-lg border border-border bg-card p-1" aria-label="Assistant panel">
                <Button className="flex-1" size="sm" variant={railTab === "assistant" ? "soft" : "ghost"} aria-pressed={railTab === "assistant"} onClick={() => setRailTab("assistant")}>Assistant</Button>
                <Button className="flex-1" size="sm" variant={railTab === "tasks" ? "soft" : "ghost"} aria-pressed={railTab === "tasks"} onClick={() => setRailTab("tasks")}>Tasks · {openTasks}</Button>
              </div>
              <div hidden={railTab !== "assistant"} className="space-y-3">
              <ChatPanel
                question={chatQuestion}
                setQuestion={setChatQuestion}
                askQuestion={askQuestion}
                messages={chatMessages}
                clearConversation={clearConversation}
                loading={chatLoading}
                aiStatus={aiStatus}
                scope={selectedProject}
                onSaveDecision={saveDecision}
                savedDecisionIds={savedDecisions}
                feedback={feedback}
                onFeedback={sendFeedback}
              />
              <details className="rounded-lg border border-border bg-card p-3"><summary className="cursor-pointer text-sm text-muted-foreground">Answer checks & provenance</summary><QualityPanel quality={chatQuality} validation={validation} /></details>
              </div>
              <div hidden={railTab !== "tasks"} className="max-h-[70vh] overflow-y-auto"><TasksPanel projects={library.projects} scope={selectedProject} onUpdateTask={updateTask} /></div>
            </aside>
          </div>
      </main>
    </div>
    <Player assets={library.assets} selected={library.assets.find(a => a.id === selectedAssetId)} seek={playerSeek} />

      <ContextMenu menu={fileMenu} onClose={() => setFileMenu(null)} />
      <ConfirmDialog
        open={assetToDelete !== null}
        title="Delete file?"
        message={
          <>
            <span className="font-medium text-foreground">{assetToDelete?.file_name}</span> will be
            removed from the library. A recovery copy will be retained in the local data folder.
          </>
        }
        onConfirm={() => {
          if (assetToDelete) doDeleteAsset(assetToDelete);
          setAssetToDelete(null);
        }}
        onCancel={() => setAssetToDelete(null)}
      />
    </div>
   </MotionConfig>
  );
}

function Header({
  theme,
  toggleTheme,
  uploadFiles,
  uploading,
  uploadOpen,
  setUploadOpen,
  projectNames
}: {
  theme: Theme;
  toggleTheme: () => void;
  uploadFiles: (form: HTMLFormElement) => void;
  uploading: boolean;
  uploadOpen: boolean;
  setUploadOpen: (open: boolean) => void;
  projectNames: string[];
}) {
  return (
    <motion.header initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="grid size-11 place-items-center rounded-lg bg-gradient-to-br from-accent to-[oklch(0.78_0.12_232)] text-accent-foreground elevate">
            <Music4 className="size-5" />
          </div>
          <div>
            <h1 className="text-xl font-semibold tracking-tight">SessionIQ</h1>
            <p className="text-sm text-muted-foreground">
              Music project notebook, analysis engine, and grounded assistant.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon"
            onClick={toggleTheme}
            aria-label="Toggle theme"
            title={theme === "dark" ? "Switch to light" : "Switch to dark"}
          >
            {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </Button>
          <Button variant={uploadOpen ? "soft" : "primary"} onClick={() => setUploadOpen(!uploadOpen)}>
            <Upload className="size-4" /> Upload files
          </Button>
        </div>
      </div>

      {uploadOpen && (
        <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}>
          <Card className="p-3">
            <form
              className="flex flex-wrap items-center gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                uploadFiles(event.currentTarget);
              }}
            >
              <input
                name="project_name"
                placeholder="Project / song — type or pick existing"
                className="input h-9 w-full sm:w-64"
                list="existing-projects"
                autoComplete="off"
              />
              <datalist id="existing-projects">
                {projectNames.map((name) => (
                  <option key={name} value={name} />
                ))}
              </datalist>
              <input name="note" placeholder="Session note" className="input h-9 w-full sm:w-56" />
              <input
                name="files"
                type="file"
                multiple
                accept="audio/*,.mid,.midi,.txt,.md,image/*"
                className="file-input"
              />
              <Button type="submit" variant="primary" disabled={uploading} className="ml-auto">
                <Upload className="size-4" /> {uploading ? "Analyzing…" : "Analyze"}
              </Button>
            </form>
          </Card>
        </motion.div>
      )}
    </motion.header>
  );
}

function ProjectOverview({ library, onSelect }: { library: LibraryResponse; onSelect: (name: string) => void }) {
  return <div className="mt-3 grid gap-2 sm:grid-cols-2 2xl:grid-cols-3">
    {library.projects.map(project => {
      const done = project.tasks.filter(t => t.status === "Done").length;
      const next = project.tasks.find(t => t.status !== "Done");
      return <button key={project.project_name} onClick={() => onSelect(project.project_name)}
        className="flex min-w-0 items-center gap-3 rounded-md border border-border bg-background/40 p-3 text-left transition-colors hover:border-accent/40 focus-visible:outline-2 focus-visible:outline-accent">
        {project.artwork ? <img src={project.artwork} alt="" className="size-12 shrink-0 rounded-md object-cover" loading="lazy" /> : <Disc3 className="size-8 shrink-0 text-accent/50" />}
        <div className="min-w-0"><p className="truncate text-sm font-semibold">{project.project_name}</p>
          <p className="mt-1 text-xs text-muted-foreground">{project.asset_count} files · {project.tasks.length ? `${done} of ${project.tasks.length} tasks done` : "No tasks yet"}</p>
          {next && <p className="mt-1 truncate text-xs text-foreground-secondary">Next: {next.description}</p>}
        </div>
      </button>;
    })}
  </div>;
}

function FiltersPanel({
  filters,
  setFilters,
  assets
}: {
  filters: Filters;
  setFilters: (filters: Filters) => void;
  assets: SessionAsset[];
}) {
  const keys = Array.from(new Set(assets.map((a) => a.key).filter(Boolean))) as string[];
  return (
    <div className="mt-4 flex flex-wrap gap-2">
      <div className="relative min-w-40 flex-[2_1_12rem]">
        <Search className="pointer-events-none absolute left-3 top-2.5 size-4 text-muted-foreground" />
        <input
          className="input has-icon"
          placeholder="Filter files"
          value={filters.query}
          onChange={(event) => setFilters({ ...filters, query: event.target.value })}
        />
      </div>
      <select
        className="input min-w-28 flex-1"
        aria-label="File type"
        value={filters.types[0] ?? ""}
        onChange={(event) => setFilters({ ...filters, types: event.target.value ? [event.target.value] : [] })}
      >
        <option value="">All types</option>
        <option>Audio</option>
        <option>MIDI</option>
        <option>Notes</option>
        <option>Image</option>
      </select>
      <select
        className="input min-w-28 flex-1"
        aria-label="File status"
        value={filters.statuses[0] ?? ""}
        onChange={(event) =>
          setFilters({ ...filters, statuses: event.target.value ? [event.target.value as FileStatus] : [] })
        }
      >
        <option value="">All statuses</option>
        {STATUSES.map((status) => (
          <option key={status}>{status}</option>
        ))}
      </select>
      <select
        className="input min-w-28 flex-1"
        aria-label="Musical key"
        value={filters.key}
        onChange={(event) => setFilters({ ...filters, key: event.target.value })}
      >
        <option value="">Any key</option>
        {keys.map((key) => (
          <option key={key}>{key}</option>
        ))}
      </select>
      <input
        className="input min-w-28 flex-1"
        placeholder="Tag"
        value={filters.tag}
        onChange={(event) => setFilters({ ...filters, tag: event.target.value })}
      />
    </div>
  );
}

function AssetTable({
  assets,
  selectedId,
  onSelect,
  onUpdate,
  onContext
}: {
  assets: SessionAsset[];
  selectedId?: string;
  onSelect: (id: string) => void;
  onUpdate: (asset: SessionAsset, update: Partial<Pick<SessionAsset, "status" | "tags">>) => void;
  onContext: (event: React.MouseEvent, asset: SessionAsset) => void;
}) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const columns = useMemo<ColumnDef<SessionAsset>[]>(
    () => [
      {
        accessorKey: "file_name",
        header: "Name",
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <TypeIcon type={row.original.display_type} />
            <span title={row.original.file_name} className="max-w-48 truncate font-medium text-foreground">{row.original.file_name}</span>
          </div>
        )
      },
      {
        accessorKey: "display_type",
        header: "Type",
        cell: ({ row }) => (
          <span className={cn("text-xs font-medium", typeTextColor(row.original.display_type))}>
            {row.original.display_type}
          </span>
        )
      },
      { accessorKey: "bpm", header: "BPM", cell: ({ row }) => row.original.bpm?.toFixed(1) ?? "—" },
      { accessorKey: "key", header: "Key", cell: ({ row }) => row.original.key ? `${row.original.key}${row.original.mode ? ` ${row.original.mode}` : ""}` : "—" },
      { accessorKey: "duration", header: "Length", cell: ({ row }) => formatSeconds(row.original.duration) },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => (
          <select
            className="select-compact"
            value={row.original.status}
            onClick={(event) => event.stopPropagation()}
            onChange={(event) => onUpdate(row.original, { status: event.target.value as FileStatus })}
          >
            {STATUSES.map((status) => (
              <option key={status}>{status}</option>
            ))}
          </select>
        )
      },
      { accessorKey: "tags", header: "Tags", cell: ({ row }) => <TagList tags={row.original.tags.slice(0, 4)} /> }
    ],
    [onUpdate]
  );

  const table = useReactTable({
    data: assets,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel()
  });

  if (!assets.length) {
    return <EmptyState message="No files match the current view. Adjust filters or upload sources." />;
  }

  return (
    <div className="mt-4 overflow-x-auto rounded-md border border-border">
      <table className="w-full text-left text-sm text-foreground-secondary">
        <thead className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th key={header.id} className={cn("px-3 py-2.5 font-medium", header.column.id === "tags" && "hidden 2xl:table-cell")}>
                  <button
                    className="flex items-center gap-1 hover:text-foreground"
                    onClick={header.column.getToggleSortingHandler()}
                  >
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    {header.column.getCanSort() && <ArrowUpDown className="size-3 opacity-50" />}
                  </button>
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.original.id}
              tabIndex={0}
              aria-label={`Inspect ${row.original.file_name}`}
              onKeyDown={event => { if (event.target === event.currentTarget && event.key === "Enter") onSelect(row.original.id); }}
              onClick={() => onSelect(row.original.id)}
              onContextMenu={(event) => onContext(event, row.original)}
              className={cn(
                "cursor-pointer border-t border-border transition-colors hover:bg-muted/50",
                row.original.id === selectedId && "bg-accent-soft/60"
              )}
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className={cn("px-3 py-2.5 align-middle", cell.column.id === "tags" && "hidden 2xl:table-cell")}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AssetGrid({
  assets,
  selectedId,
  onSelect,
  onContext
}: {
  assets: SessionAsset[];
  selectedId?: string;
  onSelect: (id: string) => void;
  onContext: (event: React.MouseEvent, asset: SessionAsset) => void;
}) {
  if (!assets.length) {
    return <EmptyState message="No files match the current view. Adjust filters or upload sources." />;
  }
  return (
    <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {assets.map((asset) => (
        <button
          key={asset.id}
          onClick={() => onSelect(asset.id)}
          onContextMenu={(event) => onContext(event, asset)}
          className={cn(
            "rounded-md border border-border bg-elevated/50 p-4 text-left transition-colors hover:border-border-strong hover:bg-elevated",
            asset.id === selectedId && "border-accent/40 bg-accent-soft/50"
          )}
        >
          <div className="mb-3 flex items-center justify-between">
            <TypeIcon type={asset.display_type} className="size-5" />
            <Badge tone={STATUS_TONE[asset.status]}>{asset.status}</Badge>
          </div>
          <div className="truncate font-medium text-foreground">{asset.file_name}</div>
          <div className="mt-1 text-sm text-muted-foreground">
            {asset.bpm ? `${asset.bpm.toFixed(1)} BPM` : "No BPM"} · {asset.key ?? "No key"}
          </div>
          <div className="mt-3">
            <TagList tags={asset.tags.slice(0, 3)} />
          </div>
        </button>
      ))}
    </div>
  );
}

const TASK_STATUSES: TaskStatus[] = ["To do", "In progress", "Almost done", "Done"];

function TasksPanel({
  projects,
  scope,
  onUpdateTask
}: {
  projects: ProjectSummary[];
  scope: string;
  onUpdateTask: (taskId: string, status: TaskStatus) => void;
}) {
  const relevant =
    scope === "All Projects"
      ? projects
      : projects.filter((p) => p.project_name === scope || p.project_name.startsWith(scope + "/"));
  const tasks = relevant.flatMap((p) => p.tasks ?? []);
  const done = tasks.filter((task) => task.status === "Done").length;

  return (
    <Card className="p-4">
      <SectionTitle
        icon={<ListChecks className="size-5" />}
        title="Tasks"
        actions={tasks.length > 0 ? <Badge tone="neutral">{done}/{tasks.length} done</Badge> : undefined}
      />
      {tasks.length === 0 ? (
        <EmptyState message="No action items yet. Add notes with 'TODO', 'fix', or 'try' to generate tasks." />
      ) : (
        <div className="mt-3 space-y-2">
          {tasks.map((task) => (
            <div key={task.id} className="rounded-md border border-border bg-background/40 p-2.5">
              <div className="flex items-start justify-between gap-2">
                <p className={cn("text-sm", task.status === "Done" && "text-muted-foreground line-through")}>
                  {task.description}
                </p>
                <select
                  className="select-compact shrink-0"
                  value={task.status}
                  onChange={(event) => onUpdateTask(task.id, event.target.value as TaskStatus)}
                >
                  {TASK_STATUSES.map((status) => (
                    <option key={status}>{status}</option>
                  ))}
                </select>
              </div>
              <p className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                <FileText className="size-3" />
                {task.source_file}
                {scope === "All Projects" && ` · ${task.project_name}`}
              </p>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function ViewTabs({ active, onChange }: { active: ViewId; onChange: (view: ViewId) => void }) {
  return (
    <div className="flex items-center gap-1 rounded-lg border border-border bg-muted/40 p-1">
      {VIEWS.map((view) => (
        <button
          key={view.id}
          onClick={() => onChange(view.id)}
          className={cn(
            "flex items-center gap-2 rounded-md px-3.5 py-1.5 text-sm font-medium transition-colors",
            active === view.id
              ? "bg-card text-foreground elevate"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          <view.icon className="size-4" />
          {view.label}
        </button>
      ))}
    </div>
  );
}

function ProjectHealthPanel({ project }: { project: ProjectSummary }) {
  const health: ProjectHealth = project.health ?? { score: 0, checks: [], suggestions: [] };
  const pct = Math.round(health.score * 100);
  const tone = pct >= 80 ? "text-success" : pct >= 50 ? "text-warning" : "text-danger";
  const barColor = pct >= 80 ? "bg-success" : pct >= 50 ? "bg-warning" : "bg-danger";
  return (
    <Card className="p-4">
      <SectionTitle
        icon={<HeartPulse className="size-5" />}
        title="Readiness checklist"
        subtitle={project.project_name}
        actions={<span className={cn("text-2xl font-semibold tracking-tight", tone)}>{pct}%</span>}
      />
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-muted">
        <div className={cn("h-full rounded-full transition-all", barColor)} style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {health.checks.map((check) => (
          <div key={check.label} className="flex items-center gap-2 text-sm">
            {check.ok ? (
              <CheckCircle2 className="size-4 text-success" />
            ) : (
              <XCircle className="size-4 text-muted-foreground/50" />
            )}
            <span className={check.ok ? "" : "text-muted-foreground"}>{check.label}</span>
          </div>
        ))}
      </div>
      {health.suggestions.length > 0 && (
        <div className="mt-4 rounded-md border border-accent/20 bg-accent-soft/40 p-3">
          <p className="mb-1.5 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-accent">
            <Lightbulb className="size-3.5" /> Suggestions
          </p>
          <ul className="space-y-1 text-sm text-muted-foreground">
            {health.suggestions.map((suggestion) => (
              <li key={suggestion} className="flex items-start gap-2">
                <span className="mt-1.5 size-1 shrink-0 rounded-full bg-accent" />
                {suggestion}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

function QualityPanel({ quality, validation }: { quality?: QualityReport; validation: any }) {
  if (!quality) {
    const pending = validation?.checks?.[0];
    return (
      <Card className="p-4">
        <SectionTitle icon={<Gauge className="size-5" />} title="Quality Report" />
        <p className="mt-3 text-sm text-muted-foreground">
          {pending?.detail ?? "Ask a question to generate a grounding + provenance report."}
        </p>
      </Card>
    );
  }
  const provenance: { label: string; value: ReactNode; icon: typeof Cpu }[] = [
    { label: "Model", value: quality.model, icon: Cpu },
    { label: "Prompt", value: quality.prompt_version, icon: FileText },
    { label: "Temperature", value: quality.temperature ?? "n/a", icon: Gauge },
    { label: "Knowledge", value: quality.knowledge_source, icon: FileAudio },
    { label: "Latency", value: `${Math.round(quality.processing_ms)} ms`, icon: Clock },
    {
      label: "Tokens",
      value: quality.token_usage?.total != null ? String(quality.token_usage.total) : "n/a",
      icon: ListChecks
    }
  ];
  return (
    <Card className="p-4">
      <SectionTitle
        icon={<Gauge className="size-5" />}
        title="Quality Report"
        actions={
          <Badge tone={quality.grounded ? "green" : "red"}>
            {quality.grounded ? "checks passed" : "review needed"}
          </Badge>
        }
      />
      <div className="mt-3 grid grid-cols-2 gap-2">
        <Stat label="Confidence" value={quality.confidence} />
        <Stat label="Hallucination risk" value={quality.hallucination_risk} />
        <Stat label="Sources retrieved" value={quality.sources_retrieved} />
        <Stat label="Files cited" value={quality.files_cited} />
      </div>

      <p className="mt-3 text-xs text-muted-foreground">Automated checks do not verify every claim or measure hallucination risk. Review the cited sources.</p>
      <div className="mt-3 space-y-1.5">
        {quality.checks.map((check) => (
          <div key={check.label} className="flex items-center gap-2 text-sm">
            {check.ok ? (
              <CheckCircle2 className="size-4 text-success" />
            ) : (
              <XCircle className="size-4 text-danger" />
            )}
            <span className={check.ok ? "" : "text-muted-foreground"}>{check.label}</span>
          </div>
        ))}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 border-t border-border pt-3">
        {provenance.map((item) => (
          <div key={item.label} className="flex items-center gap-1.5 text-xs">
            <item.icon className="size-3.5 shrink-0 text-muted-foreground" />
            <span className="text-muted-foreground">{item.label}:</span>
            <span className="truncate font-medium text-foreground">{item.value}</span>
          </div>
        ))}
        {quality.tool_calls?.length ? (
          <div className="col-span-2 flex items-center gap-1.5 text-xs">
            <Cpu className="size-3.5 shrink-0 text-muted-foreground" />
            <span className="text-muted-foreground">Metadata tools:</span>
            <span className="truncate font-medium text-foreground">
              {quality.tool_calls.map(call => call.name).join(", ")}
            </span>
          </div>
        ) : null}
      </div>
    </Card>
  );
}
