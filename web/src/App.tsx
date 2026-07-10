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
  Bot,
  Brain,
  CheckCircle2,
  Clock,
  Cpu,
  Disc3,
  FileAudio,
  FileText,
  FolderInput,
  Gauge,
  Grid2X2,
  HeartPulse,
  Image as ImageIcon,
  LayoutDashboard,
  Lightbulb,
  List,
  ListChecks,
  Moon,
  Music4,
  Plus,
  Search,
  SendHorizontal,
  Sparkles,
  StickyNote,
  Sun,
  Tag as TagIcon,
  Telescope,
  Trash2,
  Upload,
  Volume2,
  VolumeX,
  Workflow,
  X,
  XCircle
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import WaveSurfer from "wavesurfer.js";

import { Badge, Button, Card, SectionTitle, Stat } from "./components/ui";
import { ConfirmDialog, ContextMenu, type MenuState } from "./components/ContextMenu";
import { Sidebar, type GroupFilter } from "./components/Sidebar";
import { PipelineView } from "./components/Pipeline";
import { InsightsView } from "./components/Insights";
import { StudioView } from "./components/Studio";
import { readClientAudioTags } from "./lib/audioTags";
import { cn, EASE_OUT, formatSeconds } from "./lib/utils";
import type {
  AssetTag,
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

// Categorical color per file type — applied to icons so rows/cards are
// trackable by color without turning text into a rainbow.
const TYPE_META: Record<string, { color: string; Icon: typeof FileAudio }> = {
  Audio: { color: "text-type-audio", Icon: FileAudio },
  MIDI: { color: "text-type-midi", Icon: Music4 },
  Notes: { color: "text-type-note", Icon: FileText },
  Image: { color: "text-type-image", Icon: ImageIcon }
};

function TypeIcon({ type, className }: { type: string; className?: string }) {
  const meta = TYPE_META[type] ?? { color: "text-muted-foreground", Icon: FileText };
  const Icon = meta.Icon;
  return <Icon className={cn("size-4 shrink-0", meta.color, className)} />;
}

function typeTextColor(type: string): string {
  return TYPE_META[type]?.color ?? "text-muted-foreground";
}

// Named tag colors → pill styles + swatch. Users pick one when adding a tag.
const TAG_COLORS = ["neutral", "blue", "green", "amber", "red", "violet", "teal"] as const;
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
  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))];
}

export default function App() {
  const [theme, toggleTheme] = useTheme();
  const [library, setLibrary] = useState<LibraryResponse>({ assets: [], projects: [], smartCollections: {} });
  const [selectedProject, setSelectedProject] = useState<string>("All Projects");
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("table");
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [chatQuestion, setChatQuestion] = useState("");
  const [chatResult, setChatResult] = useState<any>(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [validation, setValidation] = useState<any>({ checks: [] });
  const [aiStatus, setAiStatus] = useState<any>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [activeView, setActiveView] = useState<ViewId>("workspace");
  const [pipeline, setPipeline] = useState<PipelineResponse | null>(null);
  const [fileMenu, setFileMenu] = useState<MenuState | null>(null);
  const [assetToDelete, setAssetToDelete] = useState<SessionAsset | null>(null);

  useEffect(() => {
    refreshLibrary();
    refreshValidation();
    fetch(`${API}/api/ai-status`).then((r) => r.json()).then(setAiStatus).catch(() => setAiStatus(null));
    fetch(`${API}/api/pipeline`).then((r) => r.json()).then(setPipeline).catch(() => setPipeline(null));
  }, []);

  const accent = theme === "dark" ? "oklch(0.66 0.17 256)" : "oklch(0.58 0.19 258)";
  const selectedAsset = library.assets.find((a) => a.id === selectedAssetId) ?? library.assets[0];

  const inScope = (projectName: string) =>
    selectedProject === "All Projects" ||
    projectName === selectedProject ||
    projectName.startsWith(selectedProject + "/");

  const scopedAssets = useMemo(
    () =>
      library.assets.filter((asset) => {
        if (!inScope(asset.project_name)) return false;
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
    [library.assets, selectedProject, filters]
  );

  const projectNames = library.projects.map((p) => p.project_name);
  const focusProject =
    selectedProject === "All Projects"
      ? library.projects[0]
      : library.projects.find((p) => p.project_name === selectedProject) ??
        library.projects.find((p) => p.project_name.startsWith(selectedProject + "/"));
  const chatQuality: QualityReport | undefined = chatResult?.quality;

  async function refreshLibrary() {
    const data = await (await fetch(`${API}/api/library`)).json();
    setLibrary(data);
    if (!selectedAssetId && data.assets[0]) setSelectedAssetId(data.assets[0].id);
  }

  async function refreshValidation() {
    setValidation(await (await fetch(`${API}/api/validation`)).json());
  }

  async function uploadFiles(form: HTMLFormElement) {
    const formData = new FormData(form);
    const fileInput = form.elements.namedItem("files") as HTMLInputElement | null;
    const clientTags = await readClientAudioTags(fileInput?.files ?? null);
    formData.append("client_metadata", JSON.stringify(clientTags));
    setUploading(true);
    try {
      const response = await fetch(`${API}/api/upload`, { method: "POST", body: formData });
      if (!response.ok) {
        alert((await response.json()).detail ?? "Upload failed");
        return;
      }
      await refreshLibrary();
      form.reset();
      setUploadOpen(false);
    } finally {
      setUploading(false);
    }
  }

  async function askQuestion(override?: string) {
    const question = (override ?? chatQuestion).trim();
    if (!question) return;
    if (override) setChatQuestion(override);
    setChatLoading(true);
    try {
      const response = await fetch(`${API}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          project_name: selectedProject === "All Projects" ? null : selectedProject
        })
      });
      setChatResult(await response.json());
      await refreshValidation();
    } finally {
      setChatLoading(false);
    }
  }

  async function updateAsset(asset: SessionAsset, update: Partial<Pick<SessionAsset, "status" | "tags" | "project_name" | "note">>) {
    await fetch(`${API}/api/assets/${encodeURIComponent(asset.id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update)
    });
    await refreshLibrary();
  }

  async function doDeleteAsset(asset: SessionAsset) {
    await fetch(`${API}/api/assets/${encodeURIComponent(asset.id)}`, { method: "DELETE" });
    if (selectedAssetId === asset.id) setSelectedAssetId(null);
    await refreshLibrary();
  }

  async function deleteProject(path: string) {
    await fetch(`${API}/api/projects/delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: path })
    });
    if (selectedProject === path || selectedProject.startsWith(path + "/")) {
      setSelectedProject("All Projects");
    }
    await refreshLibrary();
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
    await fetch(`${API}/api/tasks/${taskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status })
    });
    await refreshLibrary();
  }

  async function renameProject(oldName: string, newName: string) {
    await fetch(`${API}/api/projects/rename`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ old_name: oldName, new_name: newName })
    });
    if (selectedProject === oldName) setSelectedProject(newName);
    await refreshLibrary();
  }

  return (
   <MotionConfig reducedMotion="user">
    <div className="dot-grid flex h-screen overflow-hidden bg-background text-foreground">
      <Sidebar
          projects={library.projects}
          assets={library.assets}
          smartCollections={library.smartCollections}
          selectedProject={selectedProject}
          onSelectProject={(project) => {
            setSelectedProject(project);
            setFilters(EMPTY_FILTERS);
          }}
          onSelectCollection={(ids) => {
            setSelectedProject("All Projects");
            setSelectedAssetId(ids[0] ?? null);
          }}
          onRenameProject={renameProject}
          onDeleteProject={deleteProject}
          onSelectGroup={(project, filter: GroupFilter) => {
            setSelectedProject(project);
            setFilters({ ...EMPTY_FILTERS, ...filter });
          }}
        />

      <main className="flex-1 space-y-6 overflow-y-auto p-6">
          <Header
            theme={theme}
            toggleTheme={toggleTheme}
            uploadFiles={uploadFiles}
            uploading={uploading}
            uploadOpen={uploadOpen}
            setUploadOpen={setUploadOpen}
            projectNames={projectNames}
          />

          <ViewTabs active={activeView} onChange={setActiveView} />

          <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
            <motion.div
              key={activeView}
              className="space-y-6"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.22, ease: EASE_OUT }}
            >
              {activeView === "workspace" ? (
                <>
                  <ProjectOverview library={library} />
                  {focusProject && <ProjectHealthPanel project={focusProject} />}
                  <Card className="p-4">
                    <SectionTitle
                      title="File Intelligence"
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
                  <Inspector
                    asset={selectedAsset}
                    accent={accent}
                    projectNames={projectNames}
                    onUpdate={updateAsset}
                    onDelete={(asset) => setAssetToDelete(asset)}
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
            </motion.div>

            <aside className="space-y-6 xl:sticky xl:top-6">
              <ChatPanel
                question={chatQuestion}
                setQuestion={setChatQuestion}
                askQuestion={askQuestion}
                result={chatResult}
                loading={chatLoading}
                aiStatus={aiStatus}
                scope={selectedProject}
              />
              <QualityPanel quality={chatQuality} validation={validation} />
              <TasksPanel projects={library.projects} scope={selectedProject} onUpdateTask={updateTask} />
            </aside>
          </div>
      </main>

      <ContextMenu menu={fileMenu} onClose={() => setFileMenu(null)} />
      <ConfirmDialog
        open={assetToDelete !== null}
        title="Delete file?"
        message={
          <>
            <span className="font-medium text-foreground">{assetToDelete?.file_name}</span> will be
            permanently removed from disk and the library. This cannot be undone.
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

function ProjectOverview({ library }: { library: LibraryResponse }) {
  if (!library.projects.length) return null;
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {library.projects.map((project) => (
        <motion.div key={project.project_name} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
          <Card className="flex h-full flex-col overflow-hidden">
            <div className="relative h-24 w-full shrink-0 overflow-hidden border-b border-border bg-gradient-to-br from-accent/25 via-accent/5 to-elevated">
              {project.artwork ? (
                <img src={project.artwork} alt={project.project_name} className="h-full w-full object-cover" />
              ) : (
                <div className="flex h-full items-center justify-center text-accent/25">
                  <Disc3 className="size-8" />
                </div>
              )}
            </div>
            <div className="flex flex-1 flex-col p-4">
              <div className="mb-3 flex items-center justify-between gap-2">
                <h3 className="truncate font-semibold">{project.project_name}</h3>
                <Badge tone="accent">{Math.round(project.progress * 100)}%</Badge>
              </div>
              <div className="grid grid-cols-4 gap-2">
                <Stat label="Files" value={project.asset_count} />
                <Stat label="Audio" value={project.audio_count} />
                <Stat label="MIDI" value={project.midi_count} />
                <Stat label="Notes" value={project.note_count} />
              </div>
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-accent transition-all"
                  style={{ width: `${Math.max(project.progress * 100, 2)}%` }}
                />
              </div>
            </div>
          </Card>
        </motion.div>
      ))}
    </div>
  );
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
    <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-6">
      <div className="relative md:col-span-2">
        <Search className="pointer-events-none absolute left-3 top-2.5 size-4 text-muted-foreground" />
        <input
          className="input has-icon"
          placeholder="Filter files"
          value={filters.query}
          onChange={(event) => setFilters({ ...filters, query: event.target.value })}
        />
      </div>
      <select
        className="input"
        value={filters.types[0] ?? ""}
        onChange={(event) => setFilters({ ...filters, types: event.target.value ? [event.target.value] : [] })}
      >
        <option value="">All types</option>
        <option>Audio</option>
        <option>MIDI</option>
        <option>Notes</option>
      </select>
      <select
        className="input"
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
        className="input"
        value={filters.key}
        onChange={(event) => setFilters({ ...filters, key: event.target.value })}
      >
        <option value="">Any key</option>
        {keys.map((key) => (
          <option key={key}>{key}</option>
        ))}
      </select>
      <input
        className="input"
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
            <span className="truncate font-medium text-foreground">{row.original.file_name}</span>
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
      { accessorKey: "key", header: "Key", cell: ({ row }) => row.original.key ?? "—" },
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
    <div className="mt-4 overflow-hidden rounded-md border border-border">
      <table className="w-full text-left text-sm text-foreground-secondary">
        <thead className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th key={header.id} className="px-3 py-2.5 font-medium">
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
              onClick={() => onSelect(row.original.id)}
              onContextMenu={(event) => onContext(event, row.original)}
              className={cn(
                "cursor-pointer border-t border-border transition-colors hover:bg-muted/50",
                row.original.id === selectedId && "bg-accent-soft/60"
              )}
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-3 py-2.5 align-middle">
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

function Inspector({
  asset,
  accent,
  projectNames,
  onUpdate,
  onDelete
}: {
  asset?: SessionAsset;
  accent: string;
  projectNames: string[];
  onUpdate: (asset: SessionAsset, update: Partial<Pick<SessionAsset, "status" | "tags" | "project_name" | "note">>) => void;
  onDelete: (asset: SessionAsset) => void;
}) {
  if (!asset) {
    return (
      <Card className="p-4">
        <SectionTitle title="Inspector" />
        <EmptyState message="Select or upload a file to inspect its analysis." />
      </Card>
    );
  }
  const energyData = asset.audio?.energy_series.map((value, index) => ({ index, value })) ?? [];
  const centroidData = asset.audio?.spectral_centroid_series.map((value, index) => ({ index, value })) ?? [];
  const pitchData = Object.entries(asset.midi?.pitch_distribution ?? {}).map(([pitch, count]) => ({ pitch, count }));

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
          </p>
        </div>
        <div className="flex items-center gap-2">
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

      <NotesEditor asset={asset} onSave={(note) => onUpdate(asset, { note })} />

      {asset.audio?.codec && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="Codec" value={asset.audio.codec} />
          <Stat label="Peak dB" value={asset.audio.peak_db?.toFixed(1) ?? "—"} />
          <Stat label="RMS dB" value={asset.audio.rms_db?.toFixed(1) ?? "—"} />
          <Stat label="Brightness" value={asset.audio.spectral_centroid_mean?.toFixed(0) ?? "—"} />
        </div>
      )}

      {asset.media_url && asset.display_type === "Audio" && (
        <Waveform url={asset.media_url} beats={asset.audio?.beat_positions ?? []} accent={accent} />
      )}
      {energyData.length > 0 && <MiniArea title="Energy over time" data={energyData} accent={accent} />}
      {centroidData.length > 0 && <MiniArea title="Brightness over time" data={centroidData} accent={accent} />}
      {pitchData.length > 0 && (
        <ChartBlock title="MIDI pitch distribution">
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={pitchData}>
              <CartesianGrid stroke="var(--border)" vertical={false} />
              <XAxis dataKey="pitch" tick={{ fill: "var(--muted-foreground)", fontSize: 10 }} />
              <YAxis tick={{ fill: "var(--muted-foreground)", fontSize: 10 }} />
              <Tooltip
                contentStyle={{
                  background: "var(--elevated)",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  color: "var(--foreground)"
                }}
              />
              <Bar dataKey="count" fill={accent} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartBlock>
      )}
    </Card>
  );
}

function NotesEditor({ asset, onSave }: { asset: SessionAsset; onSave: (note: string) => void }) {
  const [note, setNote] = useState(asset.note ?? "");
  useEffect(() => setNote(asset.note ?? ""), [asset.id, asset.note]);
  const dirty = note !== (asset.note ?? "");
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <h3 className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground">
          <StickyNote className="size-4" /> Notes
        </h3>
        {dirty && (
          <Button variant="soft" size="sm" onClick={() => onSave(note)}>
            Save
          </Button>
        )}
      </div>
      <textarea
        className="input min-h-20 resize-y"
        placeholder="Mixing notes, ideas, to-dos… (added to the assistant's context)"
        value={note}
        onChange={(event) => setNote(event.target.value)}
      />
    </div>
  );
}

function Waveform({ url, beats, accent }: { url: string; beats: number[]; accent: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const waveRef = useRef<WaveSurfer | null>(null);
  const [playing, setPlaying] = useState(false);
  const [volume, setVolume] = useState(1);

  useEffect(() => {
    if (!containerRef.current) return;
    waveRef.current?.destroy();
    const styles = getComputedStyle(document.documentElement);
    const wave = WaveSurfer.create({
      container: containerRef.current,
      waveColor: styles.getPropertyValue("--muted-foreground").trim() || "#64748b",
      progressColor: accent,
      cursorColor: styles.getPropertyValue("--foreground").trim() || "#f8fafc",
      height: 84,
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      url
    });
    wave.on("finish", () => setPlaying(false));
    wave.once("ready", () => wave.setVolume(volume));
    waveRef.current = wave;
    return () => wave.destroy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, accent]);

  return (
    <div className="rounded-md border border-border bg-background/40 p-3">
      <div ref={containerRef} />
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button
            variant="soft"
            size="sm"
            onClick={() => {
              waveRef.current?.playPause();
              setPlaying((p) => !p);
            }}
          >
            {playing ? "Pause" : "Play"}
          </Button>
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                const next = volume > 0 ? 0 : 1;
                setVolume(next);
                waveRef.current?.setVolume(next);
              }}
              className="text-muted-foreground hover:text-foreground"
              aria-label={volume > 0 ? "Mute" : "Unmute"}
            >
              {volume > 0 ? <Volume2 className="size-4" /> : <VolumeX className="size-4" />}
            </button>
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={volume}
              onChange={(event) => {
                const next = Number(event.target.value);
                setVolume(next);
                waveRef.current?.setVolume(next);
              }}
              className="h-1 w-24 cursor-pointer accent-accent"
              aria-label="Volume"
            />
          </div>
        </div>
        <span className="text-xs text-muted-foreground">{beats.length} beat markers detected</span>
      </div>
    </div>
  );
}

function MiniArea({ title, data, accent }: { title: string; data: any[]; accent: string }) {
  return (
    <ChartBlock title={title}>
      <ResponsiveContainer width="100%" height={140}>
        <AreaChart data={data}>
          <defs>
            <linearGradient id={`grad-${title.replace(/\s/g, "")}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={accent} stopOpacity={0.35} />
              <stop offset="100%" stopColor={accent} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis dataKey="index" hide />
          <YAxis hide />
          <Tooltip
            contentStyle={{
              background: "var(--elevated)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              color: "var(--foreground)"
            }}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke={accent}
            strokeWidth={2}
            fill={`url(#grad-${title.replace(/\s/g, "")})`}
          />
        </AreaChart>
      </ResponsiveContainer>
    </ChartBlock>
  );
}

function ChartBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-medium text-muted-foreground">{title}</h3>
      {children}
    </div>
  );
}

function ChatPanel({
  question,
  setQuestion,
  askQuestion,
  result,
  loading,
  aiStatus,
  scope
}: {
  question: string;
  setQuestion: (question: string) => void;
  askQuestion: () => void;
  result: any;
  loading: boolean;
  aiStatus: any;
  scope: string;
}) {
  const suggestions = ["What still needs work?", "Which track is the fastest?", "What key do these share?"];
  return (
    <Card className="p-4 glow">
      <SectionTitle
        icon={<Bot className="size-5" />}
        title="Ask SessionIQ"
        actions={
          aiStatus && (
            <Badge tone={aiStatus.answering?.mode === "rules" ? "amber" : "green"}>
              {aiStatus.answering?.mode === "rules" ? "Rules engine" : aiStatus.answering?.model}
              {aiStatus.vector_search ? " · vector" : ""}
            </Badge>
          )
        }
      />
      <p className="mt-1 text-xs text-muted-foreground">
        Source-grounded answers scoped to <span className="text-foreground">{scope}</span>.
      </p>

      {aiStatus?.hints?.length > 0 && (
        <div className="mt-3 space-y-1 rounded-md border border-warning/25 bg-[color-mix(in_oklab,var(--warning)_8%,transparent)] p-2 text-xs text-muted-foreground">
          {aiStatus.hints.map((hint: string) => (
            <p key={hint}>{hint}</p>
          ))}
        </div>
      )}

      <div className="mt-3">
        <textarea
          className="input min-h-24 resize-none"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) askQuestion();
          }}
          placeholder="What still needs work? Which files are ready? What BPM/key do these share?"
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

      {result && (
        <motion.div
          key={result.answer.answer}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.22, ease: EASE_OUT }}
          className="mt-4 rounded-md border border-border bg-background/40 p-3 text-sm"
        >
          <p className="whitespace-pre-wrap leading-relaxed">{result.answer.answer}</p>

          {result.quality && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              <Badge tone={CONFIDENCE_TONE[result.quality.confidence] ?? "neutral"}>
                {result.quality.confidence} confidence
              </Badge>
              <Badge tone="neutral">{result.quality.model}</Badge>
              <Badge tone="neutral">prompt {result.quality.prompt_version}</Badge>
              <Badge tone="neutral">{Math.round(result.quality.processing_ms)} ms</Badge>
            </div>
          )}

          {result.answer.citations?.length > 0 && (
            <div className="mt-3 space-y-1.5 border-t border-border pt-3">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Sources</p>
              {result.answer.citations.map((citation: any) => (
                <div
                  key={`${citation.file_name}-${citation.evidence}`}
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

          {result.sources?.length > 0 && <WhyExplainer sources={result.sources} />}
        </motion.div>
      )}
    </Card>
  );
}

const CONFIDENCE_TONE: Record<string, "green" | "amber" | "red"> = {
  high: "green",
  medium: "amber",
  low: "red"
};

function WhyExplainer({ sources }: { sources: any[] }) {
  const [open, setOpen] = useState(false);
  const maxScore = Math.max(...sources.map((s) => s.score ?? 0), 0.0001);
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
            Retrieved {sources.length} source{sources.length === 1 ? "" : "s"} by relevance; the answer is grounded
            only in these.
          </p>
          {sources.map((source) => (
            <div key={source.id} className="text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-medium text-foreground">{source.file_name}</span>
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
        title="Project Health"
        subtitle={project.project_name}
        actions={<span className={cn("text-2xl font-semibold tracking-tight", tone)}>{pct}%</span>}
      />
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-muted">
        <div className={cn("h-full rounded-full transition-all", barColor)} style={{ width: `${Math.max(pct, 2)}%` }} />
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
            {quality.grounded ? "grounded" : "ungrounded"}
          </Badge>
        }
      />
      <div className="mt-3 grid grid-cols-2 gap-2">
        <Stat label="Confidence" value={quality.confidence} />
        <Stat label="Hallucination risk" value={quality.hallucination_risk} />
        <Stat label="Sources retrieved" value={quality.sources_retrieved} />
        <Stat label="Files cited" value={quality.files_cited} />
      </div>

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
      </div>
    </Card>
  );
}

function TagList({ tags }: { tags: AssetTag[] }) {
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

function TagEditor({ tags, onChange }: { tags: AssetTag[]; onChange: (tags: AssetTag[]) => void }) {
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

function EmptyState({ message }: { message: string }) {
  return (
    <div className="mt-4 rounded-md border border-dashed border-border bg-muted/30 px-4 py-10 text-center text-sm text-muted-foreground">
      {message}
    </div>
  );
}
