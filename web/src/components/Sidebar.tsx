import {
  Check,
  ChevronRight,
  Disc3,
  FileAudio,
  FileText,
  FolderOpen,
  Image as ImageIcon,
  Layers,
  Library,
  Music4,
  Pencil,
  Sparkles,
  Trash2,
  X
} from "lucide-react";
import { useMemo, useState } from "react";

import { ConfirmDialog, ContextMenu, type MenuState } from "./ContextMenu";
import { cn } from "../lib/utils";
import type { FileStatus, ProjectSummary, SessionAsset } from "../types";

export type GroupFilter = { types?: string[]; statuses?: FileStatus[] };

type GroupDef = {
  label: string;
  icon: typeof FileAudio;
  color: string;
  match: (asset: SessionAsset) => boolean;
  filter: GroupFilter;
};

const GROUPS: GroupDef[] = [
  { label: "Audio", icon: FileAudio, color: "text-type-audio", match: (a) => a.display_type === "Audio", filter: { types: ["Audio"] } },
  { label: "MIDI", icon: Music4, color: "text-type-midi", match: (a) => a.display_type === "MIDI", filter: { types: ["MIDI"] } },
  { label: "Notes", icon: FileText, color: "text-type-note", match: (a) => a.display_type === "Notes", filter: { types: ["Notes"] } },
  { label: "Artwork", icon: ImageIcon, color: "text-type-image", match: (a) => a.display_type === "Image", filter: { types: ["Image"] } },
  { label: "References", icon: Layers, color: "text-muted-foreground", match: (a) => a.status === "Reference", filter: { statuses: ["Reference"] } },
  { label: "Exports", icon: Layers, color: "text-muted-foreground", match: (a) => a.status === "Ready", filter: { statuses: ["Ready"] } }
];

type TreeNode = {
  name: string;
  path: string;
  project?: ProjectSummary;
  children: TreeNode[];
  count: number;
};

function buildTree(projects: ProjectSummary[], assets: SessionAsset[]): TreeNode[] {
  const nodes = new Map<string, TreeNode>();
  const roots: TreeNode[] = [];

  const ensure = (path: string): TreeNode => {
    const existing = nodes.get(path);
    if (existing) return existing;
    const segments = path.split("/");
    const node: TreeNode = { name: segments[segments.length - 1], path, children: [], count: 0 };
    nodes.set(path, node);
    if (segments.length === 1) {
      roots.push(node);
    } else {
      ensure(segments.slice(0, -1).join("/")).children.push(node);
    }
    return node;
  };

  for (const project of projects) ensure(project.project_name).project = project;
  for (const node of nodes.values()) {
    node.count = assets.filter(
      (a) => a.project_name === node.path || a.project_name.startsWith(node.path + "/")
    ).length;
  }
  return roots;
}

export function Sidebar({
  projects,
  assets,
  smartCollections,
  selectedProject,
  selectedCollection,
  onSelectProject,
  onSelectCollection,
  onRenameProject,
  onDeleteProject,
  onSelectGroup
}: {
  projects: ProjectSummary[];
  assets: SessionAsset[];
  smartCollections: Record<string, string[]>;
  selectedProject: string;
  selectedCollection: string | null;
  onSelectProject: (project: string) => void;
  onSelectCollection: (name: string) => void;
  onRenameProject: (oldName: string, newName: string) => void;
  onDeleteProject: (path: string) => void;
  onSelectGroup: (project: string, filter: GroupFilter) => void;
}) {
  const [openSections, setOpenSections] = useState({ projects: true, smart: true });
  const [menu, setMenu] = useState<MenuState | null>(null);
  const [pendingDelete, setPendingDelete] = useState<{ path: string; count: number } | null>(null);
  const tree = useMemo(() => buildTree(projects, assets), [projects, assets]);
  const collectionNames = Object.keys(smartCollections);

  function openContext(event: React.MouseEvent, path: string, count: number) {
    event.preventDefault();
    setMenu({
      x: event.clientX,
      y: event.clientY,
      items: [
        { label: "Open", icon: <FolderOpen className="size-4" />, onSelect: () => onSelectProject(path) },
        {
          label: "Delete",
          icon: <Trash2 className="size-4" />,
          danger: true,
          onSelect: () => setPendingDelete({ path, count })
        }
      ]
    });
  }

  return (
    <aside className="flex h-full w-full md:w-56 shrink-0 flex-col border-r border-border bg-surface/60 lg:w-60">
      <div className="flex items-center gap-2 px-4 py-4 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
        <Library className="size-4 text-accent" /> Library
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-3 pb-6">
        <RowButton
          active={selectedProject === "All Projects" && !selectedCollection}
          onClick={() => onSelectProject("All Projects")}
        >
          <FolderOpen className="size-4" />
          <span className="flex-1 truncate text-left">All Projects</span>
          <span className="text-xs text-muted-foreground">{assets.length}</span>
        </RowButton>

        <SectionHeader
          label="Projects & Albums"
          open={openSections.projects}
          onToggle={() => setOpenSections((s) => ({ ...s, projects: !s.projects }))}
        />

        {openSections.projects &&
          (tree.length ? (
            <div className="space-y-0.5">
              {tree.map((node) => (
                <TreeRow
                  key={node.path}
                  node={node}
                  depth={0}
                  assets={assets}
                  selectedProject={selectedProject}
                  onSelectProject={onSelectProject}
                  onRenameProject={onRenameProject}
                  onSelectGroup={onSelectGroup}
                  onContext={openContext}
                />
              ))}
            </div>
          ) : (
            <p className="px-3 py-2 text-xs text-muted-foreground">
              Upload a file into "Album / Song" to create your first folder.
            </p>
          ))}

        <SectionHeader
          label="Smart Collections"
          open={openSections.smart}
          onToggle={() => setOpenSections((s) => ({ ...s, smart: !s.smart }))}
        />

        {openSections.smart &&
          (collectionNames.length ? (
            collectionNames.map((name) => (
              <RowButton key={name} active={selectedCollection === name} onClick={() => onSelectCollection(name)}>
                <Sparkles className="size-4 text-accent" />
                <span className="flex-1 truncate text-left">{name}</span>
                <span className="text-xs text-muted-foreground">{smartCollections[name]?.length ?? 0}</span>
              </RowButton>
            ))
          ) : (
            <p className="px-3 py-2 text-xs text-muted-foreground">Collections appear as your library grows.</p>
          ))}
      </nav>

      <ContextMenu menu={menu} onClose={() => setMenu(null)} />
      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete project?"
        message={
          <>
            <span className="font-medium text-foreground">{pendingDelete?.path}</span> and all{" "}
            {pendingDelete?.count} file(s) inside it will be removed from the library. A recovery copy is retained in the local data folder.
          </>
        }
        onConfirm={() => {
          if (pendingDelete) onDeleteProject(pendingDelete.path);
          setPendingDelete(null);
        }}
        onCancel={() => setPendingDelete(null)}
      />
    </aside>
  );
}

function SectionHeader({ label, open, onToggle }: { label: string; open: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className="mt-3 flex w-full items-center gap-1 px-2 py-1.5 text-[0.7rem] font-semibold uppercase tracking-[0.12em] text-muted-foreground transition-colors hover:text-foreground"
    >
      <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} />
      {label}
    </button>
  );
}

function RowButton({
  active,
  onClick,
  children
}: {
  active?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-sm transition-colors",
        active ? "bg-accent-soft text-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"
      )}
    >
      {children}
    </button>
  );
}

function TreeRow({
  node,
  depth,
  assets,
  selectedProject,
  onSelectProject,
  onRenameProject,
  onSelectGroup,
  onContext
}: {
  node: TreeNode;
  depth: number;
  assets: SessionAsset[];
  selectedProject: string;
  onSelectProject: (project: string) => void;
  onRenameProject: (oldName: string, newName: string) => void;
  onSelectGroup: (project: string, filter: GroupFilter) => void;
  onContext: (event: React.MouseEvent, path: string, count: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(node.name);

  const hasChildren = node.children.length > 0;
  const active = selectedProject === node.path;
  const parentPath = node.path.includes("/") ? node.path.slice(0, node.path.lastIndexOf("/")) : "";

  // File-type groups only for leaf songs/projects (assets stored directly here).
  const directAssets = assets.filter((a) => a.project_name === node.path);
  const groups = GROUPS.map((g) => ({ ...g, count: directAssets.filter(g.match).length })).filter(
    (g) => g.count > 0
  );
  const expandable = hasChildren || groups.length > 0;

  function commit() {
    const next = draft.trim();
    setEditing(false);
    if (next && next !== node.name) {
      onRenameProject(node.path, parentPath ? `${parentPath}/${next}` : next);
    } else {
      setDraft(node.name);
    }
  }

  return (
    <div>
      <div
        className={cn(
          "group flex items-center gap-1 rounded-md py-1.5 pr-1.5 text-sm transition-colors",
          active ? "bg-accent-soft text-foreground" : "text-muted-foreground hover:bg-muted"
        )}
        style={{ paddingLeft: `${0.375 + depth * 0.75}rem` }}
        onContextMenu={(event) => onContext(event, node.path, node.count)}
      >
        <button
          onClick={() => expandable && setExpanded((v) => !v)}
          className={cn("text-muted-foreground hover:text-foreground", !expandable && "invisible")}
          aria-label={expanded ? "Collapse" : "Expand"}
        >
          <ChevronRight className={cn("size-3.5 transition-transform", expanded && "rotate-90")} />
        </button>

        {editing ? (
          <div className="flex flex-1 items-center gap-1">
            <input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") commit();
                if (e.key === "Escape") {
                  setDraft(node.name);
                  setEditing(false);
                }
              }}
              className="input h-7 flex-1 py-0.5 text-sm"
            />
            <button onClick={commit} className="text-success" aria-label="Save name">
              <Check className="size-3.5" />
            </button>
            <button
              onClick={() => {
                setDraft(node.name);
                setEditing(false);
              }}
              className="text-muted-foreground hover:text-foreground"
              aria-label="Cancel rename"
            >
              <X className="size-3.5" />
            </button>
          </div>
        ) : (
          <>
            <button
              onClick={() => onSelectProject(node.path)}
              onDoubleClick={() => setEditing(true)}
              className="flex flex-1 items-center gap-2 truncate text-left"
              title="Click to open, double-click to rename"
            >
              {hasChildren ? (
                <Disc3 className="size-4 shrink-0 text-accent" />
              ) : (
                <FolderOpen className="size-4 shrink-0" />
              )}
              <span className="truncate text-foreground/90">{node.name}</span>
            </button>
            <span className="text-xs text-muted-foreground">{node.count}</span>
            <button
              onClick={() => {
                setDraft(node.name);
                setEditing(true);
              }}
              className="text-muted-foreground/60 opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100"
              aria-label="Rename"
            >
              <Pencil className="size-3.5" />
            </button>
          </>
        )}
      </div>

      {expanded && !editing && (
        <div>
          {node.children.map((child) => (
            <TreeRow
              key={child.path}
              node={child}
              depth={depth + 1}
              assets={assets}
              selectedProject={selectedProject}
              onSelectProject={onSelectProject}
              onRenameProject={onRenameProject}
              onSelectGroup={onSelectGroup}
              onContext={onContext}
            />
          ))}
          {groups.length > 0 && (
            <div
              className="mb-1 space-y-0.5 border-l border-border"
              style={{ marginLeft: `${0.75 + depth * 0.75}rem`, paddingLeft: "0.5rem" }}
            >
              {groups.map((group) => (
                <button
                  key={group.label}
                  onClick={() => onSelectGroup(node.path, group.filter)}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                >
                  <group.icon className={cn("size-3.5", group.color)} />
                  <span className="flex-1 truncate text-left">{group.label}</span>
                  <span>{group.count}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
